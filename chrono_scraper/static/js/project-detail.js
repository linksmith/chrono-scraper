import Datepicker from 'flowbite-datepicker/Datepicker';
import projects from './projects';

export default () => ({
  deleteProject(projectId) {
    projects.deleteProject();
  },

  rebuildProjectIndex(projectId) {
    projects.rebuildProjectIndex();
  },

  initCeleryProgressBar() {},

  init() {
    this.initCeleryProgressBar();
  },
});
