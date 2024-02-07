import Datepicker from 'flowbite-datepicker/Datepicker';
import projects from './projects';

export default () => ({
  projectForm: null,
  newForm: null,
  addButton: null,
  totalForms: null,
  formNum: null,

  deleteProject(projectId) {
    projects.deleteProject();
  },

  rebuildProjectIndex(projectId) {
    projects.rebuildProjectIndex();
  },

  initDatePickers(dateInputs) {
    if (!dateInputs) {
      dateInputs = document.querySelectorAll('.dateinput');
    }
    dateInputs.forEach((input) => {
      new Datepicker(input, {
        format: 'dd-mm-yyyy',
        autohide: true,
        buttonClass: 'btn',
      });
    });
  },

  addDomain(event) {
    let newForm = this.projectForm[0]
      .querySelector('.domain-name-row')
      .cloneNode(true);
    let formRegex = RegExp(`domains-(\\d){1}-`, 'g');

    this.formNum++; //Increment the form number
    newForm.innerHTML = newForm.innerHTML.replace(
      formRegex,
      `domains-${this.formNum}-`,
    ); // Update the new form to have the correct form number
    // Set the value of the new form input to be empty
    newForm.innerHTML = newForm.innerHTML.replace(/value=".*?"/g, 'value=""');

    let parent = this.addButton.parentNode;
    parent.insertBefore(newForm, this.addButton);
    this.totalForms.setAttribute('value', `${this.formNum}`); // Increment the number of total forms in the management form

    const dateInputs = newForm.querySelectorAll('.dateinput');
    this.initDatePickers(dateInputs);
  },

  init() {
    this.projectForm = document.querySelectorAll('#project-form');
    this.container = document.querySelector('#form-container');
    this.addButton = document.querySelector('#add-domain-btn');
    this.totalForms = document.querySelector('#id_domains-TOTAL_FORMS');

    this.formNum = this.totalForms.value;

    this.initDatePickers();
  },
});
