from PIL import Image
import os

def merge_images(image1_path, image2_path, output_path):
    """Merge two images side by side and save the result."""
    try:
        image1 = Image.open(os.path.abspath(image1_path))
        image2 = Image.open(os.path.abspath(image2_path))

        # Resize second image to match height
        if image1.height != image2.height:
            ratio = image2.width / image2.height
            new_height = image1.height
            new_width = int(ratio * new_height)
            image2 = image2.resize((new_width, new_height))

        merged_width = image1.width + image2.width
        merged_image = Image.new('RGB', (merged_width, image1.height))
        merged_image.paste(image1, (0, 0))
        merged_image.paste(image2, (image1.width, 0))

        merged_image.save(os.path.abspath(output_path))
        print(f"Images merged and saved at: {os.path.abspath(output_path)}")

    except Exception as e:
        print(f"Error merging images: {e}")
