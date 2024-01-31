import utils from './utils';

export default () => ({
  projectForm: null,
  newForm: null,
  addButton: null,
  totalForms: null,
  formNum: null,

  deleteProject(projectId) {
    if (confirm('Are you sure you want to delete this project?')) {
      const csrfToken = utils.getCsrfToken();
      fetch('/api/projects/' + projectId + '/', {
        method: 'DELETE',
        headers: { 'X-CSRFToken': csrfToken },
      }).then((response) => {
        if (response.status === 204) {
          window.location.href = '/projects';
        } else {
          alert('There was an error deleting this project.');
        }
      });
    }
  },

  rebuildProjectIndex(projectId) {
    if (confirm('Are you sure you want to rebuild the project index?')) {
      const csrfToken = utils.getCsrfToken();
      fetch('/api/projects/' + projectId + '/rebuild_index/', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      }).then((response) => {
        if (response.status === 200) {
          window.location.href = '/projects';
        } else {
          alert('There was an error rebuilding the project index.');
        }
      });
    }
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
    // set value in the new form to be empty
  },

  init() {
    console.log('projects.js loaded');
    this.projectForm = document.querySelectorAll('#project-form');
    this.container = document.querySelector('#form-container');
    this.addButton = document.querySelector('#add-domain-btn');
    this.totalForms = document.querySelector('#id_domains-TOTAL_FORMS');

    this.formNum = this.totalForms.value;

    console.log('this.projectForm', this.projectForm);
    console.log('this.container', this.container);
    console.log('this.addButton', this.addButton);
    console.log('this.totalForms', this.totalForms);
    console.log('this.formNum', this.formNum);
  },
});
