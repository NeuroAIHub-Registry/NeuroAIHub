/**
 * NeuroAIHub usage log — Google Apps Script web app that appends rows to this spreadsheet.
 * Setup: see usage_logging/SETUP.md. Paste this whole file into Extensions > Apps Script of the log spreadsheet.
 *
 * Tabs: "chat" (agent questions, written by the Streamlit server; requires the secret token)
 *       "browse" (filters, charts, downloads and opened datasets, sent by the website in the visitor's browser).
 */

// Must match LOG_TOKEN in the Streamlit secrets. Change it to your own long random text.
const LOG_TOKEN = 'CHANGE-ME-to-a-long-random-text';

const COLUMNS = {
  chat: ['time_utc', 'session_id', 'turn', 'model', 'provider', 'question', 'answer', 'lookups',
         'datasets_returned', 'chart', 'status', 'seconds', 'model_calls'],
  browse: ['time_utc', 'session_id', 'action', 'search_text', 'category', 'diseases', 'modalities', 'access',
           'segmentation_mask', 'healthy_control', 'year_from', 'year_to', 'sort', 'results', 'chart_settings', 'dataset'],
};
const BROWSE_ACTIONS = ['filter', 'category_tile', 'download_csv', 'chart', 'opened_dataset', 'opened_dataset_source'];

function doPost(e) {
  let data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    return reply('bad request');
  }
  const cols = COLUMNS[data.tab];
  if (!cols) return reply('unknown tab');
  if (data.tab === 'chat' && data.token !== LOG_TOKEN) return reply('unauthorized');
  const row = data.row || {};
  if (data.tab === 'browse' && BROWSE_ACTIONS.indexOf(row.action) < 0) return reply('unknown action');

  const values = cols.map(function (c) {
    if (c === 'time_utc') return Utilities.formatDate(new Date(), 'UTC', 'yyyy-MM-dd HH:mm:ss');
    return cell(row[c], c);
  });
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const book = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = book.getSheetByName(data.tab) || book.insertSheet(data.tab);
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(cols);
      sheet.setFrozenRows(1);
    }
    sheet.appendRow(values);
  } finally {
    lock.releaseLock();
  }
  return reply('ok');
}

function cell(value, column) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'number') return value;
  let text = Array.isArray(value) ? value.join(', ') : String(value);
  // A Sheets cell holds at most 50,000 characters; questions are kept in full up to that limit.
  const limit = column === 'question' ? 49000 : 2000;
  if (text.length > limit) text = text.slice(0, limit) + '…';
  // Never let logged text run as a spreadsheet formula.
  if (/^[=+\-@]/.test(text)) text = "'" + text;
  return text;
}

function reply(message) {
  return ContentService.createTextOutput(message).setMimeType(ContentService.MimeType.TEXT);
}
