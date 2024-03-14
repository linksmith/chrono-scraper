import Alpine from 'alpinejs';

import search from './search.js';
import projectCreateUpdate from './project-create-update.js';
import projectList from './project-list.js';
import dashboard from './dashboard.js';

Alpine.data('search', search);
Alpine.data('dashboard', dashboard);
Alpine.data('projectCreateUpdate', projectCreateUpdate);
Alpine.data('projectList', projectList);

window.Alpine = Alpine;

Alpine.start();
