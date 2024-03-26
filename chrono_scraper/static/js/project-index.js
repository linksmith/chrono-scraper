import projects from './projects';

export default () => ({
  rebuildProjectIndex(projectId) {
    projects.rebuildProjectIndex();
  },

  initCeleryProgressBar() {},

  init() {
    this.initCeleryProgressBar();
  },
});
