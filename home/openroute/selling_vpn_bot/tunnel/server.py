import asyncio
import logging
import urllib.parse
from typing import Dict
import websockets
from websockets.asyncio.server import ServerConnection

try:
    from tunnel.database import verify_token, increment_data_usage
except ModuleNotFoundError:
    from database import verify_token, increment_data_usage

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TunnelProxy")

active_connections: Dict[str, int] = {}

async def ws_to_tcp(ws: ServerConnection, writer: asyncio.StreamWriter, tracker: Dict[str, int]) -> None:
    """
    Reads incoming binary frames from the WebSocket and writes them to the TCP SSH socket.
    Applies backpressure by draining the TCP socket writer buffer.
    Tracks sent bytes.
    """
    try:
        async for message in ws:
            # In SSH forwarding, payloads must be binary (bytes)
            if isinstance(message, str):
                data = message.encode('utf-8')
            else:
                data = message
            
            data_len = len(data)
            writer.write(data)
            await writer.drain()  # Apply backpressure: pause reading from WS if TCP socket buffer is full
            
            # Increment tracked bytes
            tracker["bytes"] += data_len
            
    except (websockets.exceptions.ConnectionClosed, ConnectionResetError, BrokenPipeError):
        logger.debug("WS-to-TCP: Connection closed by remote side.")
    except Exception as e:
        logger.error(f"WS-to-TCP unexpected error: {e}", exc_info=True)


async def tcp_to_ws(reader: asyncio.StreamReader, ws: ServerConnection, tracker: Dict[str, int]) -> None:
    """
    Reads data from the TCP SSH socket and sends it as binary frames over the WebSocket.
    Tracks received bytes.
    """
    try:
        while True:
            # Read up to 8KB from the local SSH daemon
            data = await reader.read(8192)
            if not data:
                # EOF reached (SSH daemon closed the connection)
                break
            
            data_len = len(data)
            await ws.send(data)
            
            # Increment tracked bytes
            tracker["bytes"] += data_len
            
    except (websockets.exceptions.ConnectionClosed, ConnectionResetError, BrokenPipeError):
        logger.debug("TCP-to-WS: Connection closed by remote side.")
    except Exception as e:
        logger.error(f"TCP-to-WS unexpected error: {e}", exc_info=True)


async def proxy_handler(ws: ServerConnection) -> None:
    """
    Core WebSocket connection handler.
    Extracts client IP, validates the token, opens a TCP channel to the user's target SSH server,
    and spawns the bidirectional streaming loops with byte counters.
    """
    # 1. Parse client IP from Nginx proxy headers
    headers = ws.request.headers
    client_ip = headers.get("X-Real-IP") or headers.get("X-Forwarded-For")
    if not client_ip:
        client_ip = ws.remote_address[0] if ws.remote_address else "unknown"
        
    logger.info(f"Incoming connection attempt from IP: {client_ip}")

    # 2. Extract and validate auth token from path query (e.g. /vpn?token=UUID)
    parsed_url = urllib.parse.urlparse(ws.request.path)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    token = query_params.get("token", [None])[0]

    if not token:
        logger.warning(f"Connection rejected from {client_ip}: Missing token query parameter.")
        await ws.close(code=1008, reason="Missing Token")
        return

    # Check database status of the user (checks exists, active, expiry, and data limit)
    res = await verify_token(token)
    if not res:
        logger.warning(f"Connection rejected from {client_ip}: Invalid, inactive, expired, or data-limit exceeded token.")
        await ws.close(code=1008, reason="Authentication Failed")
        return
    username, max_conns, target_host, target_port = res

    # Check concurrent connections limit
    current_conns = active_connections.get(username, 0)
    if current_conns >= max_conns:
        logger.warning(f"Connection rejected for '{username}' from {client_ip}: Connection limit ({max_conns}) reached (active={current_conns}).")
        await ws.close(code=1008, reason="Connection Limit Exceeded")
        return

    active_connections[username] = current_conns + 1
    logger.info(f"Authentication successful for user '{username}' (IP: {client_ip}, active_conns={current_conns + 1}/{max_conns}). Forwarding to SSH...")

    try:
        # 3. Establish TCP connection to the account's target SSH server.
        try:
            reader, writer = await asyncio.open_connection(target_host, target_port)
        except Exception as e:
            logger.error(f"Failed to connect to target SSH daemon ({target_host}:{target_port}): {e}")
            await ws.close(code=1011, reason="SSH Service Unavailable")
            return

        # 4. Spawn bidirectional proxy tasks with real-time byte tracker
        tracker = {"bytes": 0}
        ws_to_tcp_task = asyncio.create_task(ws_to_tcp(ws, writer, tracker))
        tcp_to_ws_task = asyncio.create_task(tcp_to_ws(reader, ws, tracker))

        # Wait for either pipe to exit or raise an error
        done, pending = await asyncio.wait(
            [ws_to_tcp_task, tcp_to_ws_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # 5. Clean up remaining tasks and close both connections
        logger.info(f"Session ended for user '{username}' (IP: {client_ip}). Cleaning up sockets...")
        
        for task in pending:
            task.cancel()

        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

        try:
            await ws.close()
        except Exception:
            pass

        # 6. Record data usage to SQLite database
        total_bytes = tracker["bytes"]
        if total_bytes > 0:
            logger.info(f"Recording data usage for user '{username}': {total_bytes} bytes (~{total_bytes / (1024**2):.2f} MB)")
            try:
                await increment_data_usage(username, total_bytes)
            except Exception as e:
                logger.error(f"Database error writing data usage for user '{username}': {e}")
    finally:
        active_connections[username] = max(0, active_connections.get(username, 1) - 1)


async def main() -> None:
    # Initialize DB (run updates/migrations)
    try:
        from tunnel.database import init_db
    except ModuleNotFoundError:
        from database import init_db
    try:
        await init_db()
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database: {e}")

    # Configuration constants
    import os
    BIND_HOST = "0.0.0.0"
    BIND_PORT = int(os.getenv("TUNNEL_PORT", "8745"))
    
    logger.info(f"Starting Tunnel WebSocket-to-TCP Daemon on ws://{BIND_HOST}:{BIND_PORT}...")
    
    # Launch websockets server
    # ping_interval=20 sends a WebSocket ping frame every 20 seconds.
    # ping_timeout=20 closes the connection if no pong is received within 20 seconds.
    # This prevents CDN proxy connections from idling out.
    async with websockets.asyncio.server.serve(
        proxy_handler,
        BIND_HOST,
        BIND_PORT,
        ping_interval=20,
        ping_timeout=20
    ):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Daemon stopped by user request.")
