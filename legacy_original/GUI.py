import tkinter as tk
from tkinter import filedialog, ttk
import cv2
import os
from Stenography import hide_data, unhide_data

class SteganographyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Steganography")
        self.root.configure(bg="#ffffff")
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))

        main_container = tk.Frame(root, bg="#ffffff")
        main_container.pack(expand=True, fill="both", padx=50, pady=30)

    
        header_frame = tk.Frame(main_container, bg="#ffffff")
        header_frame.pack(fill="x", pady=(0, 30))

        self.title_label = tk.Label(header_frame, text="Image Steganography", 
                                  font=("Segoe UI", 36, "bold"), fg="#2c3e50", bg="#ffffff")
        self.title_label.pack(side="left")


        separator = ttk.Separator(main_container, orient="horizontal")
        separator.pack(fill="x", pady=(0, 30))

        # Content section with two columns
        content_frame = tk.Frame(main_container, bg="#ffffff")
        content_frame.pack(fill="both", expand=True)

        # Left column for message input
        left_column = tk.Frame(content_frame, bg="#ffffff")
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 20))

        
        input_frame = tk.LabelFrame(left_column, text="Secret Message", font=("Segoe UI", 14, "bold"),
                                  fg="#2c3e50", bg="#ffffff", bd=2, relief="solid")
        input_frame.pack(fill="both", expand=True, pady=(0, 20))

        self.message_entry = tk.Text(input_frame, height=10, width=50, bg="#f8f9fa", fg="#2c3e50",
                                   font=("Segoe UI", 12), bd=0, relief="flat",
                                   highlightthickness=1, highlightbackground="#e9ecef")
        self.message_entry.pack(padx=20, pady=20, fill="both", expand=True)

     
        right_column = tk.Frame(content_frame, bg="#ffffff")
        right_column.pack(side="right", fill="y", padx=(20, 0))

        # Modern button style
        btn_style = {
            "font": ("Segoe UI", 12, "bold"),
            "bg": "#3498db",
            "fg": "#ffffff",
            "bd": 0,
            "activebackground": "#2980b9",
            "activeforeground": "#ffffff",
            "width": 20,
            "height": 2,
            "cursor": "hand2"
        }

        # Create buttons with icons (using text as icons for simplicity)
        self.select_button = tk.Button(right_column, text="Select Image", command=self.select_image, **btn_style)
        self.select_button.pack(pady=10)
        self.add_hover_effect(self.select_button)

        self.encode_button = tk.Button(right_column, text="Encode & Save", command=self.encode_message, **btn_style)
        self.encode_button.pack(pady=10)
        self.add_hover_effect(self.encode_button)

        self.decode_button = tk.Button(right_column, text="Decode Message", command=self.decode_message, **btn_style)
        self.decode_button.pack(pady=10)
        self.add_hover_effect(self.decode_button)


        status_frame = tk.Frame(main_container, bg="#f8f9fa", height=40)
        status_frame.pack(fill="x", side="bottom", pady=(20, 0))

        self.footer_label = tk.Label(status_frame, text="Ready to secure your message...", 
                                   font=("Segoe UI", 10), fg="#6c757d", bg="#f8f9fa")
        self.footer_label.pack(side="left", padx=20)

        self.image_path = ""

    def add_hover_effect(self, button):
        def on_enter(e):
            button.config(bg="#2980b9")
        def on_leave(e):
            button.config(bg="#3498db")
        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)

    def show_custom_dialog(self, title, message, is_error=False):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.configure(bg="#ffffff")
        dialog.geometry("500x300")
        dialog.grab_set()

        # Center the dialog
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'{width}x{height}+{x}+{y}')

        # Dialog content
        content_frame = tk.Frame(dialog, bg="#ffffff", padx=30, pady=20)
        content_frame.pack(fill="both", expand=True)

        # Icon and title
        icon_text = "❌" if is_error else "✅"
        icon_label = tk.Label(content_frame, text=icon_text, font=("Segoe UI", 24), 
                            fg="#e74c3c" if is_error else "#2ecc71", bg="#ffffff")
        icon_label.pack(pady=(0, 10))

        title_label = tk.Label(content_frame, text=title, font=("Segoe UI", 18, "bold"),
                             fg="#2c3e50", bg="#ffffff")
        title_label.pack(pady=(0, 20))

        # Message in a modern text box
        message_frame = tk.Frame(content_frame, bg="#f8f9fa", bd=1, relief="solid")
        message_frame.pack(fill="both", expand=True, pady=(0, 20))

        message_text = tk.Text(message_frame, wrap="word", font=("Segoe UI", 12),
                             bg="#f8f9fa", fg="#2c3e50", height=6, width=50, bd=0)
        message_text.insert("1.0", message)
        message_text.config(state="disabled")
        message_text.pack(padx=10, pady=10)

        # Modern OK button
        ok_button = tk.Button(content_frame, text="OK", font=("Segoe UI", 12, "bold"),
                            bg="#3498db", fg="#ffffff", bd=0, padx=30, pady=10,
                            activebackground="#2980b9", command=dialog.destroy,
                            cursor="hand2")
        ok_button.pack()

    def select_image(self):
        file_path = filedialog.askopenfilename(title="Select Image",
                                             filetypes=[("Image files", "*.png;*.jpg;*.jpeg")])
        if file_path:
            self.image_path = os.path.abspath(file_path)
            self.show_custom_dialog("Image Selected", f"Selected Image:\n{self.image_path}")
            self.footer_label.config(text="Image selected - Ready to encode message")

    def encode_message(self):
        if not self.image_path:
            self.show_custom_dialog("Error", "Please select an image first!", is_error=True)
            return

        data = self.message_entry.get("1.0", tk.END).strip()
        if not data:
            self.show_custom_dialog("Error", "Please enter a message to encode!", is_error=True)
            return

        output_file = filedialog.asksaveasfilename(defaultextension=".png",
                                                 filetypes=[("PNG files", "*.png")],
                                                 title="Save Encoded Image")
        if not output_file:
            return

        try:
            image = cv2.imread(self.image_path)
            encoded_image = hide_data(image, data)
            cv2.imwrite(output_file, encoded_image)
            self.show_custom_dialog("Success", f"Message encoded and saved at:\n{output_file}")
            self.footer_label.config(text="Message successfully encoded")
        except Exception as e:
            self.show_custom_dialog("Error", f"Encoding Failed:\n{str(e)}", is_error=True)
            self.footer_label.config(text="Encoding failed")

    def decode_message(self):
        file_path = filedialog.askopenfilename(title="Select Image to Decode",
                                             filetypes=[("Image files", "*.png;*.jpg;*.jpeg")])
        if not file_path:
            return

        try:
            image = cv2.imread(file_path)
            message = unhide_data(image)
            self.show_custom_dialog("Decoded Message", f"\n{message}")
            self.footer_label.config(text="Message successfully decoded")
        except Exception as e:
            self.show_custom_dialog("Error", f"Decoding Failed:\n{str(e)}", is_error=True)
            self.footer_label.config(text="Decoding failed")


if __name__ == "__main__":
    root = tk.Tk()
    app = SteganographyApp(root)
    root.mainloop()
