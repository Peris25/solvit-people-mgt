// Query parameters select from records already authorized by the API.
export const relatedRecordRows = (rows, reference) => {
  if (!reference) return rows;
  const matches = rows.filter(row => String(row.id) === reference || row.storage_id === reference);
  return matches.length === 1 ? matches : [];
};
