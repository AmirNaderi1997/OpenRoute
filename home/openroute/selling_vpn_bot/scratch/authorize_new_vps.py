import asyncio
import asyncssh
import sys

NEW_VPS_IP = "66.92.161.177"
VPS_PASSWORD = "1272510662"
PUB_KEY_PATH = "/Users/amirhossein/.ssh/id_ed25519_vpn_bot.pub"

async def main():
    print("Reading public key...")
    with open(PUB_KEY_PATH, "r") as f:
        pub_key = f.read().strip()
        
    print(f"Connecting to new VPS {NEW_VPS_IP} with password...")
    try:
        async with asyncssh.connect(
            NEW_VPS_IP,
            username="root",
            password=VPS_PASSWORD,
            known_hosts=None
        ) as conn:
            print("Connected! Setting up authorized_keys...")
            
            # Create .ssh directory and append key
            cmd = f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '{pub_key}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
            result = await conn.run(cmd)
            if result.exit_status == 0:
                print("✅ Public key authorized successfully!")
            else:
                print(f"❌ Failed to authorize key: {result.stderr}")
                sys.exit(1)
                
            # Verify system info
            res_uname = await conn.run("uname -a")
            print(f"System Info: {res_uname.stdout.strip()}")
            
    except Exception as e:
        print(f"❌ SSH Connection error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
