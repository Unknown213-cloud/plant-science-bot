import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
import post_next as bot
import publication as delivery


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.queue = self.root / "queue"
        self.posted = self.root / "posted"
        folder = self.queue / "01-test"
        folder.mkdir(parents=True)
        (folder / "caption.txt").write_text("Educational test caption", encoding="utf-8")
        for index in (1, 2):
            Image.new("RGB", (1080, 1350), (index, 2, 3)).save(folder / f"slide_{index:02}.jpg")
        self.post = bot.find_queued_posts(self.queue)[0]
        self.state = self.posted / "publication_state.json"
        self.env = patch.dict(os.environ, {"GITHUB_ACTIONS": "false"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_valid_jpeg_carousel(self):
        delivery.validate_post(self.post)

    def test_png_disguised_as_jpeg_is_rejected(self):
        Image.new("RGB", (1080, 1350)).save(self.post.slides[0], format="PNG")
        with self.assertRaisesRegex(ValueError, "RGB JPEG"):
            delivery.validate_post(self.post)

    def test_mismatched_dimensions_rejected(self):
        Image.new("RGB", (1080, 1080)).save(self.post.slides[0])
        with self.assertRaisesRegex(ValueError, "dimensions must match"):
            delivery.validate_post(self.post)

    def test_caption_limit_rejected(self):
        self.post.caption = "x" * 2201
        with self.assertRaises(ValueError):
            delivery.validate_post(self.post)

    def test_no_silent_truncation(self):
        with self.assertRaises(ValueError):
            bot.post_carousel(["url"] * 11, "caption", "unused")

    @patch.object(bot.requests, "get")
    def test_container_finished(self, get):
        get.return_value = Mock(status_code=200, json=lambda: {"status_code": "FINISHED"})
        self.assertTrue(bot.poll_media_container_status("id", "unused"))

    @patch.object(bot.requests, "get")
    def test_container_error_and_expiry_fail_closed(self, get):
        for status in ("ERROR", "EXPIRED", "PUBLISHED"):
            get.return_value = Mock(status_code=200, json=lambda: {"status_code": status})
            self.assertFalse(bot.poll_media_container_status("id", "unused"))

    def test_timeout_fails_closed(self):
        self.assertFalse(bot.poll_media_container_status("id", "unused", max_wait_sec=0))

    @patch.object(bot.time, "sleep")
    @patch.object(bot.time, "time", side_effect=[0, 0, 100])
    @patch.object(bot.requests, "get")
    def test_unknown_status_does_not_pass(self, get, clock, sleep):
        get.return_value = Mock(status_code=200, json=lambda: {"status_code": "UNKNOWN"})
        self.assertFalse(bot.poll_media_container_status("id", "unused"))

    @patch.object(bot, "poll_media_container_status", return_value=False)
    @patch.object(bot.requests, "post")
    def test_failed_child_never_publishes(self, post, poll):
        post.return_value = Mock(status_code=200, json=lambda: {"id": "child"})
        with self.assertRaisesRegex(RuntimeError, "child 1"):
            bot.post_carousel(["url1", "url2"], "caption", "unused")
        self.assertEqual(post.call_count, 1)

    @patch.object(bot, "poll_media_container_status", return_value=False)
    @patch.object(bot.requests, "post")
    def test_failed_single_never_publishes(self, post, poll):
        post.return_value = Mock(status_code=200, json=lambda: {"id": "child"})
        with self.assertRaises(RuntimeError):
            bot.post_single_image("url", "caption", "unused")
        self.assertEqual(post.call_count, 1)

    def test_journal_exists_before_publish_request(self):
        def publish(before):
            before("container")
            self.assertEqual(json.loads(self.state.read_text())[self.post.name]["status"], "publishing")
            return "media"
        archive = Mock()
        self.assertEqual(delivery.publish_once(self.post, self.state, publish, archive), "media")
        archive.assert_called_once_with("media")

    def test_ambiguous_publish_is_not_retried(self):
        def publish(before):
            before("container")
            raise TimeoutError("Response lost")
        with self.assertRaises(TimeoutError):
            delivery.publish_once(self.post, self.state, publish, Mock())
        second = Mock()
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            delivery.publish_once(self.post, self.state, second, Mock())
        second.assert_not_called()

    def test_archive_failure_recovers_without_publishing_again(self):
        def publish(before):
            before("container")
            return "media"
        with self.assertRaises(OSError):
            delivery.publish_once(self.post, self.state, publish, Mock(side_effect=OSError("disk failure")))
        second = Mock()
        archive = Mock()
        delivery.publish_once(self.post, self.state, second, archive)
        second.assert_not_called()
        archive.assert_called_once_with("media")

    @patch.object(delivery, "checkpoint", side_effect=RuntimeError("push failed"))
    def test_failed_checkpoint_prevents_publish_request(self, checkpoint):
        send = Mock()
        def publish(before):
            before("container")
            send()
            return "media"
        with self.assertRaisesRegex(RuntimeError, "push failed"):
            delivery.publish_once(self.post, self.state, publish, Mock())
        send.assert_not_called()

    @patch.object(delivery.requests, "get")
    def test_hosted_bytes_must_match(self, get):
        get.return_value = Mock(status_code=200, content=b"stale image")
        with self.assertRaisesRegex(RuntimeError, "differs"):
            delivery.verify_public_images(["https://example.test/image"], self.post.slides[:1])

    @patch.object(delivery.requests, "get")
    def test_private_or_missing_image_rejected(self, get):
        get.return_value = Mock(status_code=404)
        with self.assertRaisesRegex(RuntimeError, "publicly accessible"):
            delivery.verify_public_images(["https://example.test/image"], self.post.slides[:1])

    def test_archive_collision_preserves_existing_data(self):
        target = self.posted / self.post.name
        target.mkdir(parents=True)
        (target / "keep.txt").write_text("keep")
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            bot.move_post_to_posted(self.post, self.queue, self.posted, "media")
        self.assertTrue(self.post.path.exists())
        self.assertEqual((target / "keep.txt").read_text(), "keep")

    def test_archive_records_media_and_keeps_folder_caption_mapping(self):
        self.queue.joinpath("captions.json").write_text('{"01-test":"keep mapping"}')
        bot.move_post_to_posted(self.post, self.queue, self.posted, "media")
        self.assertEqual(json.loads((self.posted / "captions.json").read_text())[self.post.name]["media_id"], "media")
        self.assertEqual(json.loads((self.queue / "captions.json").read_text())[self.post.name], "keep mapping")

    def test_corrupt_history_does_not_move_queue(self):
        self.posted.mkdir()
        (self.posted / "captions.json").write_text("broken json")
        with self.assertRaisesRegex(RuntimeError, "unreadable"):
            bot.move_post_to_posted(self.post, self.queue, self.posted, "media")
        self.assertTrue(self.post.path.exists())


if __name__ == "__main__":
    unittest.main()
