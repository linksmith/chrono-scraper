import projects from './projects';

export default () => ({
  deleteProject(projectId) {
    projects.deleteProject(projectId);
  },

  rebuildProjectIndex(projectId) {
    projects.rebuildProjectIndex(projectId);
  },
});
