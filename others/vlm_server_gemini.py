import socket
import json
import argparse
import os
import base64
import time
from io import BytesIO
from PIL import Image
from google import genai


class GeminiVLMServer:
    def __init__(self, args):
        api_key = args.api_key or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("No API key. Set --api-key or GEMINI_API_KEY env var.")
        self.client = genai.Client(api_key=api_key)
        self.model = args.model
        print(f"[gemini] model={args.model}")

    def start_server(self, host="localhost", port=54321):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen(1)
        print(f"[gemini] server listening on {host}:{port}")

        while True:
            conn, addr = server_socket.accept()
            print(f"[gemini] connection from {addr}")
            try:
                size_data = conn.recv(8)
                size = int.from_bytes(size_data, "big")

                data = b""
                while len(data) < size:
                    packet = conn.recv(4096)
                    if not packet:
                        break
                    data += packet

                request = json.loads(data.decode())
                response = self.process_request(request["images"], request["query"])

                response_bytes = json.dumps(response).encode()
                try:
                    conn.sendall(len(response_bytes).to_bytes(8, "big"))
                    conn.sendall(response_bytes)
                except (BrokenPipeError, Exception) as e:
                    print(f"[gemini] error sending response: {e}")
            except Exception as e:
                print(f"[gemini] error handling request: {e}")
            finally:
                conn.close()

    def process_request(self, images, query):
        pil_images = []
        for img_data in images:
            if isinstance(img_data, str):
                try:
                    pil_img = Image.open(BytesIO(base64.b64decode(img_data))).convert("RGB")
                except Exception as e:
                    print(f"[gemini] error decoding image: {e}")
                    pil_img = Image.new("RGB", (224, 224), (0, 0, 0))
            else:
                pil_img = img_data
            pil_images.append(pil_img)

        num_frames = len(pil_images)
        if num_frames > 1:
            frame_desc = (
                f"You have been given {num_frames - 1} historical observation frames "
                f"followed by the current frame."
            )
        else:
            frame_desc = "You have been given the current observation frame."

        prompt = f"{frame_desc}\n{query}"

        try:
            t0 = time.time()
            response = self.client.models.generate_content(
                model=self.model,
                contents=pil_images + [prompt],
            )
            print(f"[gemini] inference took {time.time() - t0:.2f}s")
            return (response.text or "").strip()
        except Exception as e:
            print(f"[gemini] API error: {e}")
            return f"Error: {e}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=54321)
    parser.add_argument("--api-key", type=str, default=None,
                        help="Gemini API key (or set GEMINI_API_KEY env var)")
    parser.add_argument("--model", type=str, default="gemini-3-flash-preview",
                        help="Gemini model name")
    parser.add_argument("--num-video-frames", type=int, default=8)
    args = parser.parse_args()

    server = GeminiVLMServer(args)
    server.start_server(host=args.host, port=args.port)
