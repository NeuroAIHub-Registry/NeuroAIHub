/**
 * Creates the "Submit a dataset to NeuroAIHub" Google Form and its private response sheet.
 * Run it ONCE while signed in as the owner account (benyamingheiji@gmail.com): see SETUP.md.
 * The form and the sheet belong to whoever runs the script; nothing is shared with anyone.
 *
 * Question titles are matched by responses_to_csv.py — if you rename a question, rename it there too.
 */

const CATEGORIES = ['Neurodegenerative', 'Neoplasm', 'Cerebrovascular', 'Psychiatric', 'Spinal',
                    'Neurodevelopmental', 'Other / not sure'];
const MODALITIES = ['MRI', 'CT', 'PET', 'SPECT', 'X-ray', 'Ultrasound', 'DSA', 'Histology', 'Micro-CT'];
const FORMATS = ['NIFTI', 'DICOM', 'MetaImage', 'NRRD', 'Analyze', 'MINC', 'HDF5', 'PNG', 'JPG', 'TIFF'];
const YES_NO = ['Yes', 'No', 'Not sure'];

function createSubmissionForm() {
  const form = FormApp.create('Submit a dataset to NeuroAIHub');
  form.setDescription(
    'Know a public neuroradiology imaging dataset that is missing from NeuroAIHub? Tell us about it — it takes ' +
    'about 2 minutes. Only the first six questions are required; we review every submission and complete the ' +
    'remaining metadata ourselves before adding it to the database.')
    .setCollectEmail(false)
    .setAllowResponseEdits(false)
    .setLimitOneResponsePerUser(false)      // no Google sign-in needed to submit
    .setProgressBar(true)
    .setConfirmationMessage('Thank you! We will review the dataset and add it to NeuroAIHub if it fits. ' +
                            'Contributors of accepted datasets are acknowledged on GitHub.');

  const url = FormApp.createTextValidation().setHelpText('Please enter a full link starting with http(s)://')
    .requireTextIsUrl().build();

  // ---------------- required ----------------
  form.addTextItem().setTitle('Dataset name').setRequired(true)
    .setHelpText('Full name and acronym, e.g. "ISLES 2022 (Ischemic Stroke Lesion Segmentation)".');
  form.addTextItem().setTitle('Link to the dataset').setRequired(true).setValidation(url)
    .setHelpText('Where the data can be downloaded or requested (repository, challenge or project page).');
  form.addListItem().setTitle('Category').setRequired(true).setChoiceValues(CATEGORIES);
  form.addTextItem().setTitle('Disease / condition').setRequired(true)
    .setHelpText('e.g. "Glioma", "Ischemic stroke", "Alzheimer\'s disease, MCI". Write "Healthy" for healthy-volunteer datasets.');
  form.addCheckboxItem().setTitle('Imaging modality').setRequired(true).setChoiceValues(MODALITIES).showOtherOption(true);
  form.addMultipleChoiceItem().setTitle('Access').setRequired(true).setChoiceValues([
    'Open (free download, possibly after registration or a data use agreement)',
    'Restricted (application or approval required)',
    'Not sure']);

  // ---------------- optional ----------------
  form.addPageBreakItem().setTitle('Optional details')
    .setHelpText('Anything you know helps — skip whatever you are unsure about.');
  form.addTextItem().setTitle('DOI').setHelpText('DOI of the dataset or of the paper describing it, e.g. 10.1038/s41597-022-01401-7');
  form.addTextItem().setTitle('Year released').setValidation(
    FormApp.createTextValidation().setHelpText('A year such as 2024').requireNumberBetween(1980, 2100).build());
  form.addTextItem().setTitle('Number of subjects').setValidation(
    FormApp.createTextValidation().setHelpText('A whole number').requireWholeNumber().build());
  form.addTextItem().setTitle('Institution(s)');
  form.addTextItem().setTitle('Country / countries');
  form.addCheckboxItem().setTitle('Image file format').setChoiceValues(FORMATS).showOtherOption(true);
  form.addMultipleChoiceItem().setTitle('Segmentation masks / annotations included?').setChoiceValues(YES_NO);
  form.addMultipleChoiceItem().setTitle('Healthy controls included?').setChoiceValues(YES_NO);
  form.addMultipleChoiceItem().setTitle('Clinical data included?').setChoiceValues(YES_NO);
  form.addParagraphTextItem().setTitle('Other details')
    .setHelpText('e.g. MRI sequences / acquisition protocol, resolution, age range, preprocessing, histopathology or lab data.');

  // ---------------- contributor (optional) ----------------
  form.addPageBreakItem().setTitle('About you (optional)')
    .setHelpText('Only used to acknowledge you on GitHub or to ask a question about your submission. Never published without permission.');
  form.addTextItem().setTitle('Your name (for acknowledgement)');
  form.addTextItem().setTitle('Your email (if we may contact you)').setValidation(
    FormApp.createTextValidation().setHelpText('Please enter a valid email address').requireTextIsEmail().build());

  // Responses go to a new private spreadsheet in the same Drive.
  const sheet = SpreadsheetApp.create('NeuroAIHub dataset submissions (responses)');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  Logger.log('PUBLIC FORM LINK (put this on the website): ' + form.getPublishedUrl());
  Logger.log('Edit the form:   ' + form.getEditUrl());
  Logger.log('Responses sheet: ' + sheet.getUrl());
  Logger.log('Owner: ' + Session.getEffectiveUser().getEmail());
}
