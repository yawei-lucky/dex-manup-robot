import socket
import json
import argparse
import os
import base64
import time
from io import BytesIO
from PIL import Image
import dashscope
from dashscope import MultiModalConversation


class QwenVLMServer:
    def __init__(self, args):
        api_key = args.api_key or os.environ.get("DASHSCOPE_API_KEY", "") or os.environ.get("QWEN_API_KEY", "")
        if not api_key:
            raise ValueError("No API key. Set --api-key or DASHSCOPE_API_KEY env var.")
        dashscope.api_key = api_key
        self.model = args.model
        self.enable_thinking = args.enable_thinking
        print(f"[qwen] model={args.model} enable_thinking={self.enable_thinking}")

    def start_server(self, host="localhost", port=54321):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen(1)
        print(f"[qwen] server listening on {host}:{port}")

        while True:
            conn, addr = server_socket.accept()
            print(f"[qwen] connection from {addr}")
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
                    print(f"[qwen] error sending response: {e}")
            except Exception as e:
                print(f"[qwen] error handling request: {e}")
            finally:
                conn.close()

    def _images_to_data_uris(self, images):
        """Convert incoming images (base64 strings or PIL) to data: URIs without disk I/O."""
        uris = []
        for img_data in images:
            if isinstance(img_data, str):
                b64 = img_data
            else:
                buf = BytesIO()
                img_data.convert("RGB").save(buf, "JPEG", quality=90)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            uris.append(f"data:image/jpeg;base64,{b64}")
        return uris

    def process_request(self, images, query):
        image_uris = self._images_to_data_uris(images)

        num_frames = len(image_uris)
        if num_frames > 1:
            frame_desc = (
                f"You have been given {num_frames - 1} historical observation frames "
                f"followed by the current frame."
            )
        else:
            frame_desc = "You have been given the current observation frame."

        prompt = f"{frame_desc}\n{query}"

        content = [{"image": uri} for uri in image_uris]
        content.append({"text": prompt})
        messages = [{"role": "user", "content": content}]

        try:
            t0 = time.time()
            response = MultiModalConversation.call(
                model=self.model,
                messages=messages,
                enable_thinking=self.enable_thinking,
            )
            print(f"[qwen] inference took {time.time() - t0:.2f}s")
            if response.status_code != 200:
                err = f"Error: {response.code} {response.message}"
                print(f"[qwen] API error: {err}")
                return err
            text_parts = response.output.choices[0].message.content
            if isinstance(text_parts, list):
                texts = [p.get("text", "") for p in text_parts if isinstance(p, dict)]
                return "\n".join(t for t in texts if t).strip()
            return str(text_parts).strip()
        except Exception as e:
            print(f"[qwen] API error: {e}")
            return f"Error: {e}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=54321)
    parser.add_argument("--api-key", type=str, default=None,
                        help="Qwen/DashScope API key (or set DASHSCOPE_API_KEY env var)")
    parser.add_argument("--model", type=str, default="qwen3.6-flash",
                        help="Qwen VL model name (qwen3.6-flash, qwen3-vl-flash, etc)")
    parser.add_argument("--num-video-frames", type=int, default=8)
    parser.add_argument("--enable-thinking", action="store_true",
                        help="Enable Qwen3 thinking mode (slower but more reasoning). Default: off (instant mode).")
    args = parser.parse_args()

    server = QwenVLMServer(args)
    server.start_server(host=args.host, port=args.port)
