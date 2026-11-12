import pytest
from fastapi import HTTPException

from routes import employees
from .test_employee_authorization import fixture, actor, as_user, run


@pytest.mark.parametrize('role', ['hr_admin', 'hr_manager', 'general_manager'])
@pytest.mark.parametrize('employee_id', ['staff', 'other', 'boss'])
def test_hr_updates_statutory_fields_across_staff_and_records_audit(role, employee_id):
    db = fixture()
    changes = {'national_id_number': '00123456', 'kra_pin': 'A123456789Z', 'nssf_number': '000012345',
               'sha_number': 'SHA-000123', 'date_of_birth': '1994-02-14', 'gender': 'Female'}
    with as_user(employees, db, actor(role)):
        result = run(employees.update_employee(employee_id, employees.EmployeeUpdate(**changes), None))
    assert all(result[field] == value for field, value in changes.items())
    audit = db.audit_log.docs[-1]
    assert audit['entity_id'] == employee_id and audit['performed_by'] == 'user-staff'
    assert all(audit['changes'][field] == value for field, value in changes.items())


@pytest.mark.parametrize('field', ['national_id_number', 'kra_pin', 'nssf_number', 'sha_number', 'date_of_birth', 'gender'])
def test_line_manager_cannot_change_direct_reports_statutory_information(field):
    db = fixture()
    with as_user(employees, db, actor('line_manager', 'boss')):
        with pytest.raises(HTTPException) as error:
            run(employees.update_employee('staff', employees.EmployeeUpdate(**{field: 'unauthorized'}), None))
    assert error.value.status_code == 403
    assert not db.audit_log.docs


@pytest.mark.parametrize('changes', [{'date_of_birth': '2999-01-01'}, {'date_of_birth': '2020-02-30'},
    {'national_id_number': 'x' * 41}, {'sha_number': 'bad\nvalue'}])
def test_invalid_statutory_changes_do_not_save(changes):
    db = fixture()
    with as_user(employees, db, actor('hr_admin')):
        with pytest.raises(HTTPException) as error:
            run(employees.update_employee('staff', employees.EmployeeUpdate(**changes), None))
    assert error.value.status_code == 422
    assert db.employees.writes == 0
    assert not db.audit_log.docs


def test_hr_can_clear_incorrect_value_and_cannot_edit_another_tenant():
    db = fixture()
    with as_user(employees, db, actor('hr_admin')):
        result = run(employees.update_employee('staff', employees.EmployeeUpdate(sha_number=''), None))
        assert result['sha_number'] == ''
    db.employees.docs[2]['tenant_id'] = 'foreign'
    with as_user(employees, db, actor('hr_admin')):
        with pytest.raises(HTTPException) as error:
            run(employees.update_employee('other', employees.EmployeeUpdate(sha_number='blocked'), None))
    assert error.value.status_code == 404


@pytest.mark.parametrize('role', ['hr_admin', 'hr_manager', 'general_manager'])
def test_hr_edits_contacts_bank_and_employment_with_legacy_aliases(role):
    db = fixture()
    changes = {'staff_id': 'SV-001', 'probation_end_date': '2027-01-01', 'project_ownership_eligible': True,
               'personal_email': 'personal@example.com', 'phone_number': '+254700000001',
               'next_of_kin': {'name': 'Synthetic contact', 'relationship': 'Sibling', 'phone_number': '+254700000002'},
               'emergency_contact': {'name': 'Synthetic emergency', 'email': 'emergency@example.com'},
               'education': [{'institution': 'Synthetic college', 'qualification': 'Diploma', 'year': '2020'}],
               'bank_name': 'Synthetic bank', 'bank_branch': 'Nairobi', 'bank_account_number': '00001234',
               'mpesa_number': '+254700000003', 'payment_method': 'Bank Transfer'}
    with as_user(employees, db, actor(role)):
        result = run(employees.update_employee('other', employees.EmployeeUpdate(**changes), None))
    assert all(result[field] == value for field, value in changes.items())
    assert result['bank_account'] == '00001234'
    assert result['preferred_payment_method'] == 'Bank Transfer'
    assert result['employee_number'] == 'SV-001'
    assert db.audit_log.docs[-1]['entity_id'] == 'other'


@pytest.mark.parametrize('field,value', [('bank_name', 'Synthetic bank'), ('bank_branch', 'New branch'),
    ('bank_account_number', '00001234'), ('mpesa_number', '+254700000001'), ('payment_method', 'M-Pesa'),
    ('personal_email', 'other@example.com'), ('next_of_kin', {'name': 'Synthetic'}),
    ('emergency_contact', {'name': 'Synthetic'}), ('education', []), ('staff_id', 'S01'),
    ('probation_end_date', '2027-01-01'), ('project_ownership_eligible', True)])
def test_line_manager_cannot_write_new_hr_card_fields(field, value):
    db = fixture()
    with as_user(employees, db, actor('line_manager', 'boss')):
        with pytest.raises(HTTPException) as error:
            run(employees.update_employee('staff', employees.EmployeeUpdate(**{field: value}), None))
    assert error.value.status_code == 403
    assert not db.audit_log.docs


@pytest.mark.parametrize('changes', [{'personal_email': 'invalid'}, {'mpesa_number': 'abc'},
    {'bank_account_number': 'x' * 61}, {'probation_end_date': '2027-02-30'},
    {'next_of_kin': {'name': 'Synthetic', 'email': 'bad'}},
    {'education': [{'institution': 'Synthetic', 'year': 'wrong'}]}])
def test_invalid_new_card_fields_do_not_write(changes):
    db = fixture()
    with as_user(employees, db, actor('hr_admin')):
        with pytest.raises(HTTPException) as error:
            run(employees.update_employee('other', employees.EmployeeUpdate(**changes), None))
    assert error.value.status_code == 422
    assert db.employees.writes == 0


def test_unrelated_edit_does_not_discard_or_revalidate_legacy_contacts():
    db = fixture()
    db.employees.docs[2].update(education='Legacy qualification', phone_number='Legacy phone')
    with as_user(employees, db, actor('hr_admin')):
        result = run(employees.update_employee('other', employees.EmployeeUpdate(bank_name='Synthetic bank',
                     education='Legacy qualification', phone_number='Legacy phone'), None))
    assert result['education'] == 'Legacy qualification' and result['phone_number'] == 'Legacy phone'
