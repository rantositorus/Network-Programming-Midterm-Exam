import socket
import json
import base64
import logging

server_address = ('172.16.16.101', 6666)

def send_command(command_str=""):
    global server_address
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(server_address)
    logging.warning(f"connecting to {server_address}")
    try:
        sock.sendall(command_str.encode())
        data_received = ""
        while True:
            data = sock.recv(1024)
            if data:
                data_received += data.decode()
                if "\r\n\r\n" in data_received:
                    break
            else:
                break
        hasil = json.loads(data_received.strip())
        return hasil
    except:
        logging.warning("error during data receiving")
        return False

def remote_list():
    command_str = "LIST"
    hasil = send_command(command_str)
    if hasil['status'] == 'OK':
        print("Daftar file:")
        for nmfile in hasil['data']:
            print(f"- {nmfile}")
    else:
        print("Gagal:", hasil['data'])

def remote_get(filename=""):
    command_str = f"GET {filename}"
    hasil = send_command(command_str)
    if hasil['status'] == 'OK':
        namafile = hasil['data_namafile']
        isifile = base64.b64decode(hasil['data_file'])
        with open(namafile, 'wb') as f:
            f.write(isifile)
        print(f"File {namafile} berhasil diunduh.")
    else:
        print("Gagal:", hasil['data'])

def remote_upload(filename=""):
    try:
        with open(filename, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        command_str = f'UPLOAD {filename} {encoded}'
        hasil = send_command(command_str)
        print(hasil['data'])
    except Exception as e:
        print(f"Gagal upload: {e}")

def remote_delete(filename=""):
    command_str = f"DELETE {filename}"
    hasil = send_command(command_str)
    print(hasil['data'])

if __name__ == '__main__':
    # Contoh penggunaan:
    remote_list()
    remote_upload('contoh.txt')
    remote_list()
    remote_get('contoh.txt')
    remote_delete('contoh.txt')
    remote_list()
