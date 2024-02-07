import Alpine from 'alpinejs';

import search from './search.js';
import projectCreate from './project-create.js';
import projectList from './project-list.js';
import dashboard from './init-alpine.js';

Alpine.data('search', search);
Alpine.data('dashboard', dashboard);
Alpine.data('projectCreate', projectCreate);
Alpine.data('projectList', projectList);

window.Alpine = Alpine;

Alpine.start();
