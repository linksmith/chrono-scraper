import Alpine from 'alpinejs';

import search from './search.js';
import projects from './projects.js';
import dashboard from './init-alpine.js';

Alpine.data('search', search);
Alpine.data('dashboard', dashboard);
Alpine.data('projects', projects);

window.Alpine = Alpine;

Alpine.start();
