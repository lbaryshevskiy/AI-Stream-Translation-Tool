import customtkinter as ctk

def main():
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Test UI")
    root.geometry("300x200")

    label = ctk.CTkLabel(root, text="✅ CustomTkinter works!", font=("Helvetica", 14))
    label.pack(pady=20)

    button = ctk.CTkButton(root, text="Close", command=root.destroy)
    button.pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    main()
