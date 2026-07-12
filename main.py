from src.config.config_loader import load_settings


def main():

    settings = load_settings()

    print("=" * 50)
    print(settings)
    print("=" * 50)


if __name__ == "__main__":
    main()