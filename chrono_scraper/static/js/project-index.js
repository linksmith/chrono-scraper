import projects from './projects';
import utils from './utils';

export default () => ({
  messages: '',
  socket: null,

  createWebSocketComponent(data) {
    // const socket = new WebSocket(`ws://localhost:8000/task/test/`);
    // const socket = new WebSocket(`wss://chronoscraper.com/task/progress/${data.celery_task_id}/`);

    this.socket = new WebSocket(
      `ws://localhost:8000/task/progress/${data.celery_task_id}/`,
    );
    this.socket.onmessage = this.handleMessage.bind(this);
    this.socket.onerror = this.handleError.bind(this);
    this.socket.onopen = this.handleOpen.bind(this);
    this.socket.onclose = this.handleClose.bind(this);
  },

  handleMessage(event) {
    console.log('handleMessage', event.data);
    const parsedEvent = JSON.parse(event.data);
    this.messages += parsedEvent.status + '\n';
    // this.messages.push(parsedEvent.message);
  },

  handleError(event) {
    console.log(event);
  },

  handleOpen(event) {
    console.log(event);
  },

  handleClose(event) {
    console.log(event);
  },

  setProgressValue(progressValue, message, status) {
    const progressBar = document.querySelector('.progress-bar');
    const progressMessage = document.querySelector('.progress-message');
    const progressStatus = document.querySelector('.progress-status');

    progressBar.style.width = progressValue + '%';
    progressBar.setAttribute('aria-valuenow', progressValue);
    progressMessage.innerText = message;
    progressStatus.innerText = status;
  },

  rebuildProjectIndex(projectId) {
    const csrfToken = utils.getCsrfToken();
    fetch('/api/projects/' + projectId + '/rebuild_index/', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken },
    })
      .then((response) => {
        if (response.status === 200) {
          console.info('Rebuilding the project index...');
          return response.json();
        } else {
          console.error('There was an error rebuilding the project index.');
        }
      })
      .then((data) => {
        this.createWebSocketComponent(data);
        //
        //
        // socket.onmessage = (event) => {
        //     console.log("socket.onmessage")
        //     const parsedEvent = JSON.parse(event.data);
        //     console.log("socket.onmessage", parsedEvent.progress * 100, parsedEvent.message, parsedEvent.status)
        //     this.setProgressValue(
        //         parsedEvent.progress * 100,
        //         parsedEvent.message,
        //         parsedEvent.status
        //     );
        // };
      });
  },
});
