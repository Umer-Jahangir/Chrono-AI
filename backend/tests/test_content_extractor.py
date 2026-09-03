import io
import json
import unittest

from docx import Document

from app.services.content_extractor import UnsupportedContentType, extract_text


class ContentExtractorTests(unittest.TestCase):
    def test_plain_text_is_normalized(self):
        self.assertEqual(extract_text(b"hello   world\n\n\nnext", "note.txt", "text/plain"), "hello world\n\nnext")

    def test_json_is_searchable(self):
        result = extract_text(json.dumps({"project": "Chrono"}).encode(), "data.json", "application/json")
        self.assertIn("Chrono", result)

    def test_csv_rows_become_lines(self):
        result = extract_text(b"name,value\nalpha,42\n", "data.csv", "text/csv")
        self.assertEqual(result, "name\tvalue\nalpha\t42")

    def test_docx_paragraphs_are_extracted(self):
        document = Document()
        document.add_paragraph("Chrono document content")
        stream = io.BytesIO()
        document.save(stream)
        result = extract_text(stream.getvalue(), "document.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertEqual(result, "Chrono document content")

    def test_binary_type_is_skipped(self):
        with self.assertRaises(UnsupportedContentType):
            extract_text(b"binary", "photo.png", "image/png")


if __name__ == "__main__":
    unittest.main()
