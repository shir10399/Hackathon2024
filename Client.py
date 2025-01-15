import socket
import struct
import threading
import time


# ANSI color codes for output formatting
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


# Constants for communication
MAGIC_COOKIE = 0xabcddcba  # Identifier for valid packets
MESSAGE_TYPE_OFFER = 0x2  # Message type for server offers
MESSAGE_TYPE_REQUEST = 0x3  # Message type for client requests
MESSAGE_TYPE_PAYLOAD = 0x4  # Message type for data payload
BROADCAST_PORT = 13117  # UDP broadcast port
BUFFER_SIZE = 4096  # Size of data chunks

# List to store connection statistics
connection_stats = []


def startup():
    """
    Collect and validate user input for file size and number of connections.
    Ensures all inputs are positive integers.
    Returns:
        tuple: file_size (int), tcp_connections (int), udp_connections (int)
    """
    while True:
        try:
            file_size = int(input(f"{Colors.OKCYAN}Enter file size (bytes): {Colors.ENDC}"))
            if file_size <= 0:
                raise ValueError("File size must be positive.")
            break
        except ValueError as e:
            print(f"{Colors.WARNING}Invalid input: {e}. Try again.{Colors.ENDC}")

    while True:
        try:
            tcp_connections = int(input(f"{Colors.OKCYAN}Enter number of TCP connections: {Colors.ENDC}"))
            if tcp_connections < 0:
                raise ValueError("TCP connections must be non-negative.")
            break
        except ValueError as e:
            print(f"{Colors.WARNING}Invalid input: {e}. Try again.{Colors.ENDC}")

    while True:
        try:
            udp_connections = int(input(f"{Colors.OKCYAN}Enter number of UDP connections: {Colors.ENDC}"))
            if udp_connections < 0:
                raise ValueError("UDP connections must be non-negative.")
            break
        except ValueError as e:
            print(f"{Colors.WARNING}Invalid input: {e}. Try again.{Colors.ENDC}")

    return file_size, tcp_connections, udp_connections


def listen_for_offers():
    """
    Listen for server broadcast offers over UDP.
    Returns:
        tuple: server_ip (str), udp_port (int), tcp_port (int)
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as udp_socket:
        # Set the socket to allow broadcast
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_socket.bind(('', BROADCAST_PORT))  # Bind to the broadcast port

        print(f"{Colors.OKBLUE}[Client] Listening for server offers...{Colors.ENDC}")
        while True:
            try:
                # Receive and unpack offer data
                data, addr = udp_socket.recvfrom(BUFFER_SIZE)
                magic_cookie, message_type, udp_port, tcp_port = struct.unpack('!IBHH', data[:10])
                if magic_cookie == MAGIC_COOKIE and message_type == MESSAGE_TYPE_OFFER:
                    print(
                        f"{Colors.OKGREEN}[Client] Received offer from {addr[0]}: UDP Port {udp_port}, TCP Port {tcp_port}{Colors.ENDC}")
                    return addr[0], udp_port, tcp_port
            except Exception as e:
                print(f"{Colors.WARNING}[Client] Error receiving offer: {e}{Colors.ENDC}")


def tcp_transfer(server_ip, tcp_port, file_size, transfer_id):
    """
    Perform a single TCP transfer.
    Args:
        server_ip (str): Server IP address.
        tcp_port (int): Server TCP port.
        file_size (int): Requested file size.
        transfer_id (int): Transfer identifier for logging.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.connect((server_ip, tcp_port))
            tcp_socket.sendall(f"{file_size}\n".encode())

            start_time = time.time()
            total_received = 0

            # Receive data in chunks
            while total_received < file_size:
                data = tcp_socket.recv(min(BUFFER_SIZE, file_size - total_received))
                if not data:
                    break
                total_received += len(data)

            elapsed_time = time.time() - start_time
            try:
                speed = (total_received * 8) / elapsed_time  # Convert to bits/second
            except ZeroDivisionError:
                speed = (total_received * 8) / 0.0099
            connection_stats.append({"type": "TCP", "file_size": file_size, "speed": speed})
            print(
                f"{Colors.OKGREEN}TCP transfer #{transfer_id} finished, total time: {elapsed_time:.2f} seconds, total "
                f"speed: {speed:.2f} bits/second{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}[Client] Error during TCP transfer #{transfer_id}: {e}{Colors.ENDC}")


def udp_transfer(server_ip, udp_port, file_size, transfer_id):
    """
    Perform a single UDP transfer.
    Args:
        server_ip (str): Server IP address.
        udp_port (int): Server UDP port.
        file_size (int): Requested file size.
        transfer_id (int): Transfer identifier for logging.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
            udp_socket.settimeout(1)
            request_message = struct.pack('!IBQ', MAGIC_COOKIE, MESSAGE_TYPE_REQUEST, file_size)
            udp_socket.sendto(request_message, (server_ip, udp_port))

            total_segments = file_size // BUFFER_SIZE + (1 if file_size % BUFFER_SIZE != 0 else 0)
            received_segments = set()
            start_time = time.time()

            # Receive data packets
            while True:
                try:
                    data, _ = udp_socket.recvfrom(BUFFER_SIZE + 21)
                    magic_cookie, message_type, total_segments, current_segment = struct.unpack('!IBQQ', data[:21])
                    if magic_cookie == MAGIC_COOKIE and message_type == MESSAGE_TYPE_PAYLOAD:
                        received_segments.add(current_segment)
                except socket.timeout:
                    break

            elapsed_time = time.time() - start_time
            success_rate = (len(received_segments) / total_segments) * 100
            speed = (len(received_segments) * BUFFER_SIZE * 8) / elapsed_time  # Convert to bits/second
            connection_stats.append({"type": "UDP", "file_size": file_size, "speed": speed})
            print(
                f"{Colors.OKGREEN}UDP transfer #{transfer_id} finished, total time: {elapsed_time:.2f} seconds, total speed: {speed:.2f} bits/second,\
                 percentage of packets received successfully: {success_rate:.2f}%{Colors.ENDC}")

    except Exception as e:
        print(f"{Colors.FAIL}[Client] Error during UDP transfer #{transfer_id}: {e}{Colors.ENDC}")


def speed_test(server_ip, tcp_port, udp_port, file_size, tcp_connections, udp_connections):
    """
    Perform multiple TCP and UDP transfers as part of the speed test.
    Args:
        server_ip (str): Server IP address.
        tcp_port (int): Server TCP port.
        udp_port (int): Server UDP port.
        file_size (int): Requested file size for each transfer.
        tcp_connections (int): Number of TCP connections.
        udp_connections (int): Number of UDP connections.
    """
    threads = []

    # Start TCP threads
    for i in range(tcp_connections):
        thread = threading.Thread(target=tcp_transfer, args=(server_ip, tcp_port, file_size, i + 1))
        threads.append(thread)
        thread.start()

    # Start UDP threads
    for i in range(udp_connections):
        thread = threading.Thread(target=udp_transfer, args=(server_ip, udp_port, file_size, i + 1))
        threads.append(thread)
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    print(f"{Colors.OKBLUE}[Client] All transfers complete. Listening for new offers...{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Collected Statistics: {connection_stats}{Colors.ENDC}")


if __name__ == "__main__":
    file_size, tcp_connections, udp_connections = startup()
    server_ip, udp_port, tcp_port = listen_for_offers()
    speed_test(server_ip, tcp_port, udp_port, file_size, tcp_connections, udp_connections)