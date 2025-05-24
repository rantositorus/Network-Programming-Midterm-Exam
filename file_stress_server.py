import socket
from concurrent.futures import ThreadPoolExecutor
from file_protocol import FileProtocol
import base64
import os
import multiprocessing
from dotenv import load_dotenv

load_dotenv()

SERVER_PORT = int(os.getenv("port_server", "6666"))
class Server:
    def __init__(self, ip='0.0.0.0', port=SERVER_PORT, max_workers=5, mode="thread"):
        self.ip = ip
        self.port = port
        self.mode = mode
        self.max_workers = max_workers
        self.protocol = FileProtocol()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.ip, self.port))
        self.sock.listen(100)

        if mode == "thread":
            self.pool = ThreadPoolExecutor(max_workers=max_workers)

    def handle_client(self, conn, addr):
        try:
            buffer = b""
            while True:
                data = conn.recv(1024 * 1024)
                if not data:
                    break
                buffer += data
                if b"\r\n\r\n" in buffer:
                    break

            command_str = buffer.decode(errors="ignore").strip()
            print(f"[SERVER] Received {len(buffer)} bytes from {addr}")

            if command_str.startswith("UPLOAD"):
                try:
                    parts = command_str.split(" ", 2)
                    if len(parts) != 3:
                        raise ValueError("Invalid UPLOAD format")
                    _, filename, encoded = parts
                    filedata = base64.b64decode(encoded)
                    os.makedirs("uploads", exist_ok=True)
                    filepath = os.path.join("uploads", filename)
                    with open(filepath, "wb") as f:
                        f.write(filedata)
                    response = {"status": "OK", "data": f"File {filename} uploaded successfully"}
                except Exception as e:
                    print(f"[SERVER] Upload error: {e}")
                    response = {"status": "ERROR", "data": f"Upload failed: {str(e)}"}

            elif command_str.startswith("GET"):
                try:
                    parts = command_str.split(" ", 1)
                    if len(parts) != 2:
                        raise ValueError("Invalid GET format")
                    _, filename = parts
                    filepath = os.path.join("uploads", filename)
                    if not os.path.exists(filepath):
                        raise FileNotFoundError(f"{filename} not found")

                    with open(filepath, "rb") as f:
                        filedata = f.read()
                        encoded = base64.b64encode(filedata).decode()
                    response = {"status": "OK", "data_file": encoded}
                except Exception as e:
                    print(f"[SERVER] Download error: {e}")
                    response = {"status": "ERROR", "data": f"Download failed: {str(e)}"}

            else:
                try:
                    result = self.protocol.proses_string(command_str)
                    if isinstance(result, dict):
                        response = result
                    else:
                        response = {"status": "OK", "data": result}
                except Exception as e:
                    response = {"status": "ERROR", "data": f"Command error: {str(e)}"}

            conn.sendall((str(response).replace("'", '"') + "\r\n\r\n").encode())
        except Exception as e:
            print(f"[SERVER] General error with {addr}: {e}")
        finally:
            conn.close()

    def serve_forever(self):
        print(f"[SERVER-{self.mode.upper()}] Listening on port {self.port} with PID {os.getpid()}...")
        while True:
            conn, addr = self.sock.accept()
            if self.mode == "thread":
                self.pool.submit(self.handle_client, conn, addr)
            elif self.mode == "process":
                # langsung handle di proses ini
                self.handle_client(conn, addr)

    def run(self):
        if self.mode == "thread":
            print(f"[SERVER] Running in THREAD mode with {self.max_workers} workers...")
            self.serve_forever()
        elif self.mode == "process":
            print(f"[SERVER] Running in PROCESS mode with {self.max_workers} processes...")
            processes = []
            for _ in range(self.max_workers):
                p = multiprocessing.Process(target=self.serve_forever)
                p.start()
                processes.append(p)

            for p in processes:
                p.join()

def main():
    print("==== FILE SERVER CONFIGURATION ====")
    print("Pilih metode eksekusi:")
    print("1. Multithreading")
    print("2. Multiprocessing")

    mode_input = input("Pilihan [1/2]: ").strip()
    mode = "thread" if mode_input != "2" else "process"

    print("\nPilih jumlah worker:")
    print("1. 1")
    print("2. 5")
    print("3. 50")
    worker_input = input("Pilihan [1/2/3]: ").strip()
    worker_map = {"1": 1, "2": 5, "3": 50}
    workers = worker_map.get(worker_input, 5)

    port = SERVER_PORT
    server = Server(port=port, max_workers=workers, mode=mode)
    server.run()

if __name__ == '__main__':
    multiprocessing.set_start_method("fork")  # atau "spawn" untuk Windows
    main()
