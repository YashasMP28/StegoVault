import cv2
import numpy as np
import os
from Convert_Image import *

DELIMITER = '#####'

def to_binary(message):
    """Convert message to binary."""
    if isinstance(message, str):
        try:
            message.encode('ascii')
        except UnicodeEncodeError:
            raise TypeError('Input type not supported (Non-ASCII characters)')
        return ''.join([format(ord(i), '08b') for i in message])
    elif isinstance(message, (bytes, np.ndarray)):
        return [format(i, '08b') for i in message]
    elif isinstance(message, (int, np.uint8)):
        return format(message, '08b')
    else:
        raise TypeError('Input type not supported')

def hide_data(image, secret_message):
    """Hide secret message inside image."""
    n_bytes = (image.shape[0] * image.shape[1] * 3 * 2) // 8
    print(f"Maximum bytes to encode: {n_bytes}")
    if len(secret_message) > n_bytes:
        raise ValueError('Error: Insufficient bytes. Need bigger image or less data.')

    secret_message += DELIMITER
    secret_message = to_binary(secret_message)
    data_index = 0

    for row in image:
        for pixel in row:
            for n in range(3):  # R, G, B
                if data_index < len(secret_message):
                    bin_pixel = to_binary(pixel[n])
                    # Use last 2 bits for data instead of just 1
                    if data_index + 1 < len(secret_message):
                        pixel[n] = int(bin_pixel[:-2] + secret_message[data_index:data_index+2], 2)
                        data_index += 2
                    else:
                        pixel[n] = int(bin_pixel[:-1] + secret_message[data_index], 2)
                        data_index += 1
            if data_index >= len(secret_message):
                break
        if data_index >= len(secret_message):
            break
    return image

def unhide_data(image):
    """Retrieve hidden message from image."""
    binary_data = ''
    for row in image:
        for pixel in row:
            for n in range(3):
                bin_pixel = to_binary(pixel[n])
                # Extract last 2 bits instead of just 1
                binary_data += bin_pixel[-2:]

    all_bytes = [binary_data[i:i+8] for i in range(0, len(binary_data), 8)]
    decoded_data = ''
    for byte in all_bytes:
        if len(byte) == 8:  # Only process complete bytes
            decoded_data += chr(int(byte, 2))
            if decoded_data.endswith(DELIMITER):
                break
    return decoded_data[:-5]

def display_image(image, title):
    resized = cv2.resize(image, (500, 500))
    cv2.imshow(title, resized)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

def encode_text():
    input_path = input('Enter input image path: ')
    if not os.path.exists(input_path):
        print("Image not found.")
        return
    image = cv2.imread(input_path)
    display_image(image, "Original Image")

    message = input('Enter data to encode: ')
    if not message:
        print("No message entered.")
        return

    output_path = input('Enter output image path (PNG recommended): ')
    encoded_image = hide_data(image, message)
    cv2.imwrite(output_path, encoded_image)
    print(f"Message encoded. Output saved at {os.path.abspath(output_path)}")

def decode_text():
    input_path = input('Enter input image path: ')
    if not os.path.exists(input_path):
        print("Image not found.")
        return
    image = cv2.imread(input_path)
    display_image(image, "Encoded Image")
    message = unhide_data(image)
    print(f"Decoded message: {message}")

def menu():
    print("\n--- Image Steganography ---")
    print("1. Encode text in image")
    print("2. Decode text from image")
    print("3. Convert JPEG to PNG")
    print("4. Convert RGB to Grayscale")
    print("5. Merge two images")
    print("6. Exit")
    choice = input("Enter your choice: ")
    return choice

def main():
    while True:
        choice = menu()
        if choice == '1':
            encode_text()
        elif choice == '2':
            decode_text()
        elif choice == '3':
            input_path = input("Enter JPEG image path: ")
            output_path = input("Enter output PNG path: ")
            jpeg_to_png(input_path, output_path)
        elif choice == '4':
            input_path = input("Enter image path: ")
            output_path = input("Enter grayscale image path: ")
            rgb_to_grayscale(input_path, output_path)
        elif choice == '5':
            image1 = input("Enter first image path: ")
            image2 = input("Enter second image path: ")
            output = input("Enter merged image path: ")
            from mergingimage import merge_images
            merge_images(image1, image2, output)
        elif choice == '6':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Try again.")

if __name__ == "__main__":
    main()
