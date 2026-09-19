from .server import mcp
from .enhanced import register


def main() -> None:
    register(mcp)
    mcp.run()


if __name__ == "__main__":
    main()
