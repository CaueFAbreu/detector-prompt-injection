import importlib


def test_pacote_src_importavel():
    assert importlib.import_module("src") is not None
