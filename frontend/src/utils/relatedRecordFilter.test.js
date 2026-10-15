import { relatedRecordRows } from './relatedRecordFilter';
const rows = [{ id: 'canonical', title: 'Own' }, { id: '507f1f77bcf86cd799439011', title: 'Legacy' }];
test('normal module list is preserved without a notification target', () => expect(relatedRecordRows(rows, '')).toBe(rows));
test('linked canonical and legacy record identifiers select only an existing authorized row', () => {
  expect(relatedRecordRows(rows, 'canonical')).toEqual([rows[0]]);
  expect(relatedRecordRows(rows, '507f1f77bcf86cd799439011')).toEqual([rows[1]]);
});
test('unknown or unauthorized targets cannot introduce another record', () => expect(relatedRecordRows(rows, 'forged')).toEqual([]));
test('storage aliases select one authorized record and ambiguous aliases select none', () => {
  expect(relatedRecordRows([{ id: 'canonical', storage_id: 'mongo' }], 'mongo')).toHaveLength(1);
  expect(relatedRecordRows([{ id: 'mongo' }, { id: 'canonical', storage_id: 'mongo' }], 'mongo')).toEqual([]);
});
