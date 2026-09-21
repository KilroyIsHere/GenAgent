try:
    import PIL
    from PIL import Image
    print("PIL_VERSION", PIL.__version__)
except Exception as e:
    print("NO_PIL", repr(e))
