import http.server
import socketserver
import os

# Define configuration
PORT = 8080
DIRECTORY = "/storage/emulated/0/"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # This ensures the server looks in the correct directory
        super().__init__(*args, directory=DIRECTORY, **kwargs)

try:
    # Set up the server on localhost
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Serving files from {DIRECTORY}")
        print(f"Access at: http://localhost:{PORT}")
        httpd.serve_forever()
except PermissionError:
    print("Error: You do not have permission to access this directory.")
except FileNotFoundError:
    print(f"Error: The directory {DIRECTORY} was not found.")
except Exception as e:
    print(f"An error occurred: {e}")
