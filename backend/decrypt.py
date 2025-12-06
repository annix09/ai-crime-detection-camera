from cryptography.fernet import Fernet
from pathlib import Path


FERNET_KEY_FILE = "fernet.key"   
EVIDENCE_DIR = Path("evidence") 
DECRYPTED_DIR = Path("decrypted_videos")
DECRYPTED_DIR.mkdir(exist_ok=True)


key = Path(FERNET_KEY_FILE).read_text().strip()
fernet = Fernet(key.encode())


enc_files = list(EVIDENCE_DIR.glob("*.enc"))

if not enc_files:
    print("No encrypted files found in evidence/")
else:
    for enc_file in enc_files:
        print(f"Decrypting {enc_file.name}...")
        enc_data = enc_file.read_bytes()
        try:
            decrypted_data = fernet.decrypt(enc_data)
         
            original_name = enc_file.stem  
            out_path = DECRYPTED_DIR / original_name
            out_path.write_bytes(decrypted_data)
            print(f"Saved decrypted video as {out_path}")
        except Exception as e:
            print(f"Failed to decrypt {enc_file.name}: {e}")

print("Done!")
