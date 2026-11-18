import json
import socket

SOCKET_PATH = "/tmp/pokemon-adaptive-ost-test.sock"


def main():
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(2)

    try:
        connection.connect(SOCKET_PATH)
        print("Connected to MPV!")

        command = {
            "command": ["get_property", "idle-active"],
            "request_id": 1
        }

        connection.sendall((json.dumps(command) + "\n").encode())

        # Read MPV's response
        response = b""

        while not response.endswith(b"\n"):
            chunk = connection.recv(4096)

            if not chunk:
                break

            response += chunk

        result = json.loads(response.decode())

        print("MPV response:")
        print(json.dumps(result, indent=4))

    finally:
        connection.close()


if __name__ == "__main__":
    main()