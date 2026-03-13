from PIL import Image
import os

def expand_image(input_path, output_path):
    try:
        if not os.path.exists(input_path):
            print(f"Error: Input file not found at {input_path}")
            return

        # Open the image
        img = Image.open(input_path)
        print(f"Original image size: {img.size}")
        
        # Crop 540x120 from top-left (0, 0)
        # We need a 540x120 patch to tile 2x12 times to get 1080x1440
        crop_width = 540
        crop_height = 120
        
        # Ensure image is large enough
        if img.width < crop_width or img.height < crop_height:
            print(f"Warning: Image is smaller than crop size ({crop_width}x{crop_height}). Resizing to fit crop size first.")
            img = img.resize((max(img.width, crop_width), max(img.height, crop_height)))
            
        patch = img.crop((0, 0, crop_width, crop_height))
        print(f"Cropped patch size: {patch.size}")
        
        # Target size
        target_width = 1080
        target_height = 1440
        
        # Create new blank image
        new_img = Image.new('RGB', (target_width, target_height))
        
        # Calculate grid size
        cols = target_width // crop_width  # 1080 / 540 = 2
        rows = target_height // crop_height # 1440 / 120 = 12
        
        print(f"Tiling {cols}x{rows} grid...")
        
        for x in range(cols):
            for y in range(rows):
                # Paste the patch at the calculated position
                position = (x * crop_width, y * crop_height)
                new_img.paste(patch, position)
                
        # Save the result
        new_img.save(output_path)
        print(f"Successfully saved expanded image to: {os.path.abspath(output_path)}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Input image path provided by user
    input_file = r"C:\Users\lenovo\Desktop\5.png"
    
    # Output file in the current directory (temp_image_expand)
    output_file = os.path.join(os.path.dirname(__file__), "expanded_1080x1440.png")
    
    expand_image(input_file, output_file)
