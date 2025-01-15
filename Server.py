import socket
import threading
import struct
import time

# Constants
MAGIC_COOKIE = 0xabcddcba  # Unique identifier to validate packets
MESSAGE_TYPE_OFFER = 0x2  # Message type for "offer"
MESSAGE_TYPE_REQUEST = 0x3  # Message type for "request"
MESSAGE_TYPE_PAYLOAD = 0x4  # Message type for "payload"
BROADCAST_PORT = 13117  # Port used for broadcasting
BUFFER_SIZE = 1024*1024  # Chunk size for pipelined transfers


def get_broadcast_ip():
    """
    Dynamically determine the broadcast IP address of the current network.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))  # Connect to a public DNS server to get the local IP
    local_ip = s.getsockname()[0]
    s.close()

    # Get the network prefix and calculate the broadcast address
    ip_parts = local_ip.split('.')
    broadcast_ip = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.255"  # Assuming a /24 network
    return broadcast_ip


def broadcast_offers(udp_port, tcp_port):
    """
    Continuously send broadcast messages offering server availability.
    Args:
        udp_port (int): The UDP port for client requests.
        tcp_port (int): The TCP port for client requests.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        broadcast_ip = get_broadcast_ip()  # Dynamically get the broadcast IP
        while True:
            try:
                message = struct.pack('!IBHH', MAGIC_COOKIE, MESSAGE_TYPE_OFFER, udp_port, tcp_port)
                udp_socket.sendto(message, (broadcast_ip, BROADCAST_PORT))
                print(f"[Server] Offer broadcasted on UDP Port {udp_port}, TCP Port {tcp_port}")
                time.sleep(1)
            except Exception as e:
                print(f"[Server] Error broadcasting offer: {e}")


def handle_tcp_connection(client_socket):
    """
    Handle a single TCP connection using pipelined data transfer.
    Args:
        client_socket (socket): Socket representing the client connection.
    """
    try:
        request = client_socket.recv(BUFFER_SIZE).decode().strip()
        file_size = int(request)
        print(f"[Server] Received TCP request for {file_size} bytes.")

        total_sent = 0
        while total_sent < file_size:
            chunk = b"0" * min(BUFFER_SIZE, file_size - total_sent)
            client_socket.sendall(chunk)
            total_sent += len(chunk)

        print(f"[Server] Sent {file_size} bytes over TCP.")
    except Exception as e:
        print(f"[Server] Error in TCP connection: {e}")
    finally:
        client_socket.close()


def handle_udp_connection(udp_socket, client_address, file_size):
    """
    Handle a UDP request to send data in segments.

    Args:
        udp_socket (socket): The UDP socket for communication.
        client_address (tuple): The address of the client (IP, port).
        file_size (int): The total size of the data requested by the client.
    """

    total_segments = file_size // BUFFER_SIZE + (1 if file_size % BUFFER_SIZE != 0 else 0)
    try:
        for i in range(total_segments):
            # Prepare and send each segment
            segment = struct.pack('!IBQQ', MAGIC_COOKIE, MESSAGE_TYPE_PAYLOAD, total_segments,
                                  i + 1) + b"X" * BUFFER_SIZE
            udp_socket.sendto(segment, client_address)
            time.sleep(0.001)  # Simulate network delay for each packet
        print(f"[Server] Sent {total_segments} UDP segments to {client_address}.")
    except Exception as e:
        print(f"[Server] Error in UDP connection: {e}")


def start_server():
    """
    Start the server, broadcast offers, and handle client requests.
    """
    print("[Server] Starting...")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket, \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:

        tcp_socket.bind(("", 0))
        udp_socket.bind(("", 0))

        server_ip = socket.gethostbyname(socket.gethostname())
        tcp_port = tcp_socket.getsockname()[1]
        udp_port = udp_socket.getsockname()[1]

        print(f"[Server] Server started, listening on IP address {server_ip}")
        print(f"[Server] TCP listening on port {tcp_port}.")
        print(f"[Server] UDP listening on port {udp_port}.")

        threading.Thread(target=broadcast_offers, args=(udp_port, tcp_port), daemon=True).start()

        tcp_socket.listen(5)
        while True:
            client_conn, _ = tcp_socket.accept()
            threading.Thread(target=handle_tcp_connection, args=(client_conn,), daemon=True).start()

            data, client_address = udp_socket.recvfrom(BUFFER_SIZE)
            try:
                magic_cookie, message_type, file_size = struct.unpack('!IBQ', data)
                if magic_cookie == MAGIC_COOKIE and message_type == MESSAGE_TYPE_REQUEST:
                    threading.Thread(target=handle_udp_connection, args=(udp_socket, client_address, file_size),
                                     daemon=True).start()
            except Exception as e:
                print(f"[Server] Malformed UDP request from {client_address}: {e}")


if __name__ == "__main__":
    start_server()
