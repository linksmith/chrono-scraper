import utils from './utils';

export default {
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
          console.error('There was an error deleting this project.');
        }
      });
    }
  },
};
