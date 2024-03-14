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

  rebuildProjectIndex(projectId) {
    if (confirm('Are you sure you want to rebuild the project index?')) {
      const csrfToken = utils.getCsrfToken();
      fetch('/api/projects/' + projectId + '/rebuild_index/', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      }).then((response) => {
        if (response.status === 200) {
          console.info('Rebuilding the project index...', response.body);
        } else {
          console.error('There was an error rebuilding the project index.');
        }
      });
    }
  },
};
