import socket
import json
import base64
import logging
import os
import time
import concurrent.futures
import statistics
import csv
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

SERVER_IP = os.getenv("ip_server", "127.0.0.1")
SERVER_PORT = int(os.getenv("port_server", "6666"))

class InteractiveStressTester:
    def __init__(self):
        self._setup_directories()
        self.logger = self._configure_logging()
        self.server_address = self._get_server_address()
        self.test_results = []

    def _setup_directories(self) -> None:
        os.makedirs('test_files', exist_ok=True)
        os.makedirs('downloads', exist_ok=True)

    def _configure_logging(self) -> logging.Logger:
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler("stress_test.log"),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)

    def _get_server_address(self) -> tuple:
        print("\n" + "="*40)
        print("Server Configuration")
        print("="*40)
        host = SERVER_IP
        print(f"Server IP: {host}")
        port = SERVER_PORT
        print(f"Server Port: {port}")
        return (host, int(port))

    def _get_test_parameters(self) -> Dict:
        params = {}

        print("\n" + "="*40)
        print("Test Parameters")
        print("="*40)

        file_size_options = [10, 50, 100]
        print("File Size Options (MB):")
        for idx, size in enumerate(file_size_options, 1):
            print(f"{idx}. {size} MB")
        print(f"{len(file_size_options)+1}. All")
        size_choices = input("Choose file sizes (comma separated, e.g. 1,3 or 4 for all): ")
        try:
            if size_choices.strip() == str(len(file_size_options)+1):
                params['file_sizes'] = file_size_options
            else:
                indices = [int(s.strip())-1 for s in size_choices.split(',')]
                params['file_sizes'] = [file_size_options[i] for i in indices if 0 <= i < len(file_size_options)]
        except Exception:
            params['file_sizes'] = [file_size_options[0]]  # default 10MB

        print("\nClient Pool Sizes:")

        print("\nClient Pool Sizes:")
        print("1. 1\n2. 5\n3. 50\n4. All (1,5,50)")
        client_choice = input("Choose option (1-4): ").strip()
        client_options = {'1': [1], '2': [5], '3': [50], '4': [1, 5, 50]}
        params['client_pools'] = client_options.get(client_choice, [1])

        print("\nServer Pool Sizes:")
        print("1. 1\n2. 5\n3. 50")
        server_choice = input("Choose option (1-3): ").strip()
        server_options = {'1': [1], '2': [5], '3': [50]}
        params['server_pools'] = server_options.get(server_choice, [1])

        print("\nExecutor Type:")
        print("1. Threads\n2. Processes\n3. Both")
        exec_choice = input("Choose executor type (1-3): ").strip()
        params['executor'] = ['thread', 'process', 'both'][int(exec_choice)-1]

        return params

    def _generate_test_file(self, size_mb: int) -> str:
        filename = f"test_file_{size_mb}MB.bin"
        filepath = os.path.join('test_files', filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) == size_mb * 1024 * 1024:
            return filepath

        self.logger.info(f"Generating test file: {filename} ({size_mb}MB)")
        with open(filepath, 'wb') as f:
            for _ in range(size_mb):
                f.write(os.urandom(1024 * 1024))
        return filepath

    def _send_command(self, command_str: str = "") -> dict:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(600)
        try:
            sock.connect(self.server_address)
            for i in range(0, len(command_str), 65536):
                sock.sendall(command_str[i:i+65536].encode())
            sock.sendall("\r\n\r\n".encode())

            data_received = ""
            while True:
                data = sock.recv(1024*1024)
                if data:
                    data_received += data.decode()
                    if "\r\n\r\n" in data_received:
                        break
                else:
                    break
            json_response = data_received.split("\r\n\r\n")[0]
            return json.loads(json_response)
        except Exception as e:
            return {'status': 'ERROR', 'data': str(e)}
        finally:
            sock.close()

    def _perform_upload(self, file_path: str, worker_id: int) -> dict:
        start = time.time()
        try:
            file_size = os.path.getsize(file_path)
            self.logger.info(f"Worker {worker_id}: Uploading {os.path.basename(file_path)} ({file_size/1024/1024:.2f} MB)")
            with open(file_path, 'rb') as fp:
                content = base64.b64encode(fp.read()).decode()
            cmd = f"UPLOAD {os.path.basename(file_path)} {content}"
            result = self._send_command(cmd)
            duration = time.time() - start
            throughput = file_size / duration if duration > 0 else 0
            self.logger.info(f"Worker {worker_id}: Upload completed in {duration:.2f}s, {throughput/1024/1024:.2f} MB/s")
            return {
                'worker_id': worker_id, 'operation': 'upload', 'file_size': file_size,
                'duration': duration, 'throughput': throughput,
                'status': result['status'], 'error': result.get('data', '') if result['status'] != 'OK' else ''
            }
        except Exception as e:
            duration = time.time() - start
            self.logger.error(f"Worker {worker_id}: Upload failed - {e}")
            return {
                'worker_id': worker_id, 'operation': 'upload', 'file_size': 0,
                'duration': duration, 'throughput': 0,
                'status': 'ERROR', 'error': str(e)
            }

    def _perform_download(self, file_name: str, worker_id: int) -> dict:
        start = time.time()
        try:
            self.logger.info(f"Worker {worker_id}: Downloading {file_name}")
            result = self._send_command(f"GET {file_name}")
            duration = time.time() - start
            if result['status'] == 'OK':
                filedata = base64.b64decode(result['data_file'])
                with open(os.path.join('downloads', f"{worker_id}_{file_name}"), 'wb') as f:
                    f.write(filedata)
                throughput = len(filedata) / duration if duration > 0 else 0
                self.logger.info(f"Worker {worker_id}: Download completed in {duration:.2f}s, {throughput/1024/1024:.2f} MB/s")
                return {
                    'worker_id': worker_id, 'operation': 'download', 'file_size': len(filedata),
                    'duration': duration, 'throughput': throughput,
                    'status': 'OK', 'error': ''
                }
            else:
                return {
                    'worker_id': worker_id, 'operation': 'download', 'file_size': 0,
                    'duration': duration, 'throughput': 0,
                    'status': 'ERROR', 'error': result.get('data', '')
                }
        except Exception as e:
            duration = time.time() - start
            return {
                'worker_id': worker_id, 'operation': 'download', 'file_size': 0,
                'duration': duration, 'throughput': 0,
                'status': 'ERROR', 'error': str(e)
            }

    def _run_test(self, operation: str, config: Dict) -> List[Dict]:
        results = []
        for server_pool in config['server_pools']:
            print(f"\n[!] Configure server with {server_pool} workers and press ENTER to continue...")
            input()
            for file_size in config['file_sizes']:
                file_path = self._generate_test_file(file_size)
                for client_pool in config['client_pools']:
                    executors = ['thread', 'process'] if config['executor'] == 'both' else [config['executor']]
                    for executor in executors:
                        print(f"\nRunning {operation} test - File: {file_size}MB, Clients: {client_pool}, Executor: {executor}")
                        executor_cls = (concurrent.futures.ThreadPoolExecutor if executor == 'thread' else concurrent.futures.ProcessPoolExecutor)
                        all_results = []
                        with executor_cls(max_workers=client_pool) as executor_obj:
                            if operation == 'upload':
                                futures = [executor_obj.submit(self._perform_upload, file_path, i) for i in range(client_pool)]
                            else:
                                if not self._ensure_file_exists(file_path):
                                    print("Failed to upload test file for download operation")
                                    continue
                                futures = [executor_obj.submit(self._perform_download, os.path.basename(file_path), i) for i in range(client_pool)]
                            for future in concurrent.futures.as_completed(futures):
                                try:
                                    all_results.append(future.result())
                                except Exception as e:
                                    all_results.append({
                                        'worker_id': -1, 'operation': operation, 'file_size': 0,
                                        'duration': 0, 'throughput': 0,
                                        'status': 'ERROR', 'error': str(e)
                                    })
                        stats = self._calculate_statistics(all_results, operation, file_size, client_pool, server_pool, executor)
                        results.append(stats)
                        print("\n=== Test Results ===")
                        for k, v in stats.items():
                            print(f"{k:20}: {v}")
        return results

    def _ensure_file_exists(self, file_path: str) -> bool:
        try:
            with open(file_path, 'rb') as fp:
                content = base64.b64encode(fp.read()).decode()
            cmd = f"UPLOAD {os.path.basename(file_path)} {content}"
            result = self._send_command(cmd)
            return result['status'] == 'OK'
        except Exception:
            return False

    def _calculate_statistics(self, results: List[Dict], operation: str, file_size: int, client_pool: int, server_pool: int, executor: str) -> Dict:
        durations = [r['duration'] for r in results if r['status'] == 'OK']
        throughputs = [r['throughput'] for r in results if r['status'] == 'OK']
        return {
            'operation': operation,
            'file_size_mb': file_size,
            'client_pool_size': client_pool,
            'server_pool_size': server_pool,
            'executor_type': executor,
            'success_count': sum(1 for r in results if r['status'] == 'OK'),
            'fail_count': sum(1 for r in results if r['status'] != 'OK'),
            'avg_duration': statistics.mean(durations) if durations else 0,
            'median_duration': statistics.median(durations) if durations else 0,
            'min_duration': min(durations) if durations else 0,
            'max_duration': max(durations) if durations else 0,
            'avg_throughput': statistics.mean(throughputs) if throughputs else 0,
            'median_throughput': statistics.median(throughputs) if throughputs else 0,
            'min_throughput': min(throughputs) if throughputs else 0,
            'max_throughput': max(throughputs) if throughputs else 0,
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def _save_results(self) -> str:
        if not self.test_results:
            print("No results to save!")
            return ""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"stress_results_{timestamp}.csv"
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = list(self.test_results[0].keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.test_results:
                writer.writerow(row)
        print(f"\nResults saved to {filename}")
        return filename

    def run(self):
        print("\n" + "="*40)
        print("File Server Stress Tester")
        print("="*40)
        params = self._get_test_parameters()
        self.test_results.extend(self._run_test('upload', params))
        self.test_results.extend(self._run_test('download', params))
        self._save_results()
        print("\nTesting complete. Exiting...")

if __name__ == "__main__":
    try:
        tester = InteractiveStressTester()
        tester.run()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Error: {str(e)}")