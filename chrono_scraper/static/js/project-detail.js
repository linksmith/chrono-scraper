import projects from './projects';

export default () => ({
  deleteProject(projectId) {
    projects.deleteProject();
  },

  rebuildProjectIndex(projectId) {
    projects.rebuildProjectIndex();
  },

  init() {},
});
