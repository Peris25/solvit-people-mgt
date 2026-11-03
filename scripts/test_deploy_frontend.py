import ftplib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import deploy_frontend as deploy


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'static/js').mkdir(parents=True)
        (self.root / 'static/js/main.hash.js').write_bytes(b'compiled app')
        (self.root / 'index.html').write_text('<script src="/static/js/main.hash.js"></script>', encoding='utf-8')

    def test_assets_before_atomic_index_and_no_deletion(self):
        ftp = MagicMock()
        deploy.publish(ftp, self.root)
        self.assertEqual(ftp.rename.call_args_list[-1].args, ('index.html.uploading', 'index.html'))
        self.assertEqual(ftp.storbinary.call_count, 2)
        ftp.delete.assert_not_called()
        ftp.rmd.assert_not_called()

    def test_missing_build_and_private_files_fail_before_upload(self):
        for name in ('.env', 'secret.pem', 'source.js.map', 'records.csv', 'payload.php'):
            with self.subTest(name=name):
                path = self.root / name
                path.write_text('not public', encoding='utf-8')
                ftp = MagicMock()
                with self.assertRaises(ValueError):
                    deploy.publish(ftp, self.root)
                ftp.storbinary.assert_not_called()
                path.unlink()
        (self.root / 'index.html').unlink()
        with self.assertRaises(ValueError):
            deploy.build_files(self.root)

    def test_create_missing_asset_directory(self):
        ftp = MagicMock()
        ftp.cwd.side_effect = [None, ftplib.error_perm('missing'), None, None, None]
        deploy.publish(ftp, self.root)
        ftp.mkd.assert_called_once_with('static')

    @patch.object(deploy.time, 'sleep')
    @patch.object(deploy, 'fetch')
    def test_live_verification_requires_matching_asset_bytes(self, fetch, sleep):
        fetch.side_effect = lambda url: (self.root / 'index.html').read_bytes() if '?release=' in url else b'compiled app'
        deploy.verify(self.root)
        fetch.side_effect = lambda url: (self.root / 'index.html').read_bytes() if '?release=' in url else b'old app'
        with self.assertRaises(ValueError):
            deploy.verify(self.root)

    @patch.object(deploy, 'verify')
    @patch.object(deploy.ftplib, 'FTP_TLS')
    @patch.dict(deploy.os.environ, {'FTP_HOST': 'ftp.example.com', 'FTP_USER': 'test', 'FTP_PASSWORD': 'synthetic'})
    @patch.object(deploy, 'build_files')
    @patch.object(deploy, 'publish', return_value=2)
    def test_verified_tls_and_encrypted_data_required(self, publish, files, factory, verify):
        deploy.main()
        context = factory.call_args.kwargs['context']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, deploy.ssl.CERT_REQUIRED)
        ftp = factory.return_value.__enter__.return_value
        ftp.prot_p.assert_called_once()
        publish.assert_called_once()


if __name__ == '__main__':
    unittest.main()
