from PIL import Image
import os

def jpeg_to_png(input_path, output_path):
    """Convert JPEG image to PNG format."""
    try:
        img = Image.open(os.path.abspath(input_path))
        img.save(os.path.abspath(output_path), format='PNG')
        print(f"Image converted and saved at: {os.path.abspath(output_path)}")
    except Exception as e:
        print(f"Error converting JPEG to PNG: {e}")

def rgb_to_grayscale(input_path, output_path):
    """Convert RGB image to Grayscale."""
    try:
        img = Image.open(os.path.abspath(input_path))
        gray_img = img.convert('L')
        gray_img.save(os.path.abspath(output_path))
        print(f"Grayscale image saved at: {os.path.abspath(output_path)}")
    except Exception as e:
        print(f"Error converting to Grayscale: {e}")
