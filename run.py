"""
EXE 빌드 및 직접 실행용 진입점.
프로젝트 루트에 위치해 PyInstaller가 src 패키지를 올바르게 찾을 수 있도록 한다.
"""
from src.main import main

if __name__ == "__main__":
    main()
