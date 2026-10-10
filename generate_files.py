from pathlib import Path
import argparse


def generate_files(folder_path: str, start_index: int, count: int = 20):
    folder = Path(folder_path)

    # Tạo folder nếu chưa tồn tại
    folder.mkdir(parents=True, exist_ok=True)

    for index in range(start_index, start_index + count):
        file_path = folder / f"{index}_vi.txt"

        # Không ghi đè file đã tồn tại
        if file_path.exists():
            print(f"[SKIP] {file_path.name} already exists")
            continue

        file_path.touch()
        print(f"[CREATE] {file_path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate sequential *_vi.txt files"
    )

    parser.add_argument(
        "folder_path",
        help="Path to the folder"
    )

    parser.add_argument(
        "start_index",
        type=int,
        help="Starting index"
    )

    args = parser.parse_args()

    generate_files(
        folder_path=args.folder_path,
        start_index=args.start_index,
        count=20
    )