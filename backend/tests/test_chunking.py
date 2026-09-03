import unittest

from app.services.chunking import chunk_text, normalize_embedding_text, split_for_embedding


class ChunkingTests(unittest.TestCase):
    def test_empty_text_has_no_chunks(self):
        self.assertEqual(chunk_text(""), [])

    def test_chunks_overlap_and_preserve_order(self):
        text = " ".join(f"word{i}" for i in range(500))
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.token_count <= 100 for chunk in chunks))
        self.assertEqual([chunk.index for chunk in chunks], list(range(len(chunks))))

    def test_invalid_overlap_is_rejected(self):
        with self.assertRaises(ValueError):
            chunk_text("hello", chunk_size=10, overlap=10)

    def test_embedding_text_normalizes_invalid_unicode_and_controls(self):
        normalized = normalize_embedding_text("safe\ud800text\x00end")
        self.assertNotIn("\ud800", normalized)
        self.assertNotIn("\x00", normalized)
        normalized.encode("utf-8")

    def test_oversized_embedding_text_is_split_below_limit(self):
        pieces = split_for_embedding("token " * 2500, token_limit=2048)
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(piece.token_count < 2048 for piece in pieces))


if __name__ == "__main__":
    unittest.main()
