from utils.solver_cv import available_cv_path
from utils.solver_candidates import projection
from routes import solver_intake


def test_existing_private_cv_is_available_in_both_projections(tmp_path,monkeypatch):
    monkeypatch.setenv('CV_UPLOAD_ROOT',str(tmp_path))
    monkeypatch.setattr(solver_intake,'CV_UPLOAD_ROOT',tmp_path)
    file=tmp_path/'synthetic.pdf';file.write_bytes(b'synthetic')
    row={'id':'synthetic','cv_path':str(file)}
    assert available_cv_path(row)==file
    for result in (projection(row,True,True),solver_intake._serialise(row)):
        assert result['has_cv'] is True and 'cv_path' not in result


def test_missing_or_outside_cv_is_unavailable_without_changing_records(tmp_path,monkeypatch):
    root=tmp_path/'private';root.mkdir()
    monkeypatch.setenv('CV_UPLOAD_ROOT',str(root))
    monkeypatch.setattr(solver_intake,'CV_UPLOAD_ROOT',root)
    outside=tmp_path/'outside.pdf';outside.write_bytes(b'synthetic')
    directory=root/'directory.pdf';directory.mkdir()
    for value in (None,'',str(root/'missing.pdf'),str(outside),str(directory),'bad\x00path'):
        row={'id':'synthetic','cv_path':value}
        before=dict(row)
        assert available_cv_path(row) is None
        for result in (projection(row,True,True),solver_intake._serialise(row)):
            assert result['has_cv'] is False and 'cv_path' not in result
        assert row==before
