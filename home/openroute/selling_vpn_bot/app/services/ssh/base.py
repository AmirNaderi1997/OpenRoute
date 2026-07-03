from abc import ABC, abstractmethod

class BaseSSHManager(ABC):
    """
    Abstract base class for SSH manager.
    Implementations should handle connecting to the remote server and executing shell commands
    for user provisioning and management.
    """

    @abstractmethod
    async def create_system_user(self, server_ip: str, username: str, password: str, expire_days: int) -> bool:
        """
        Creates a system user on the remote server with the specified expiry.
        Should run `useradd`, `chpasswd`, and `chage`.
        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    async def lock_user(self, server_ip: str, username: str) -> bool:
        """
        Locks the user account on the remote server when the account expires or is disabled.
        Should run `usermod -L` and potentially kill active sessions.
        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    async def get_user_traffic(self, server_ip: str, username: str) -> int:
        """
        Returns the outbound traffic in bytes for the specified user.
        """
        pass
