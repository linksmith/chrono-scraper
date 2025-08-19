<script lang="ts">
	import { onMount } from 'svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
	import { Switch } from '$lib/components/ui/switch';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Separator } from '$lib/components/ui/separator';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Info, CheckCircle, AlertCircle, Zap, Shield, Globe, Clock } from 'lucide-svelte';

	interface EntityBackendOption {
		backend: string;
		name: string;
		description: string;
		supported_languages: string[];
		entity_types: string[];
		speed: string;
		accuracy: string;
		cost: string;
		requires_api_key: boolean;
		requires_internet: boolean;
		max_text_length?: number;
		pros: string[];
		cons: string[];
		available: boolean;
		config_schema?: any;
	}

	interface UserEntityConfig {
		enabled: boolean;
		backend: string;
		language: string;
		backend_config: Record<string, any>;
		enable_wikidata: boolean;
		wikidata_language: string;
		confidence_threshold: number;
		enable_entity_types: string[];
		max_entities_per_page: number;
		enable_context_extraction: boolean;
	}

	// Component state
	let config: UserEntityConfig = {
		enabled: false,
		backend: 'enhanced_spacy',
		language: 'en',
		backend_config: {},
		enable_wikidata: true,
		wikidata_language: 'en',
		confidence_threshold: 0.7,
		enable_entity_types: ['person', 'organization', 'location', 'event'],
		max_entities_per_page: 100,
		enable_context_extraction: true
	};

	let backends: EntityBackendOption[] = [
		{
			backend: 'enhanced_spacy',
			name: 'Enhanced spaCy (Recommended)',
			description: 'Advanced multilingual entity recognition with Dutch and English support',
			supported_languages: ['en', 'nl', 'xx'],
			entity_types: ['person', 'organization', 'location', 'event', 'product', 'date', 'money', 'email', 'url'],
			speed: 'fast',
			accuracy: 'high',
			cost: 'free',
			requires_api_key: false,
			requires_internet: false,
			max_text_length: 1000000,
			pros: [
				'✅ Free to use - no API costs',
				'✅ Excellent Dutch and English support',
				'✅ Fast processing speed (~120ms per page)',
				'✅ Works offline - no internet required',
				'✅ High accuracy for standard entities',
				'✅ Built-in context extraction',
				'✅ Privacy-friendly - all processing local'
			],
			cons: [
				'❌ Limited to Dutch and English languages',
				'❌ Requires spaCy model downloads (~500MB)',
				'❌ Weaker on very specialized entity types',
				'❌ No built-in entity linking to knowledge bases'
			],
			available: true
		},
		{
			backend: 'firecrawl_extraction',
			name: 'Firecrawl AI Extraction',
			description: 'LLM-powered structured entity extraction with rich context understanding',
			supported_languages: ['en', 'nl', 'de', 'fr', 'es', 'it', 'pt', 'pl', 'ru', 'zh', 'ja'],
			entity_types: ['person', 'organization', 'location', 'event', 'product', 'concept'],
			speed: 'medium',
			accuracy: 'research',
			cost: 'low',
			requires_api_key: false,
			requires_internet: true,
			max_text_length: 100000,
			pros: [
				'✅ Highest accuracy entity extraction',
				'✅ Excellent multilingual support (11+ languages)',
				'✅ Rich context understanding and relationships',
				'✅ Handles complex entity types and nested structures',
				'✅ Uses local Firecrawl instance - no external API costs',
				'✅ Custom schema support for domain-specific entities',
				'✅ Built-in entity relationship detection'
			],
			cons: [
				'❌ Slower processing (~500ms per page)',
				'❌ Requires Firecrawl service to be running',
				'❌ Higher memory usage for complex extractions',
				'❌ May over-extract in some cases',
				'❌ Dependent on Firecrawl service availability'
			],
			available: true,
			config_schema: {
				type: 'object',
				properties: {
					firecrawl_url: {
						type: 'string',
						default: 'http://localhost:3002',
						description: 'Firecrawl service URL'
					},
					extraction_timeout: {
						type: 'integer',
						default: 30,
						description: 'Timeout in seconds for extraction'
					}
				}
			}
		}
	];

	let selectedBackend: EntityBackendOption;
	let loading = false;
	let saveStatus: 'idle' | 'saving' | 'success' | 'error' = 'idle';

	$: selectedBackend = backends.find(b => b.backend === config.backend) || backends[0];

	const entityTypes = [
		{ value: 'person', label: 'Persons', icon: '👤' },
		{ value: 'organization', label: 'Organizations', icon: '🏢' },
		{ value: 'location', label: 'Locations', icon: '📍' },
		{ value: 'event', label: 'Events', icon: '📅' },
		{ value: 'product', label: 'Products', icon: '📦' },
		{ value: 'date', label: 'Dates', icon: '📅' },
		{ value: 'money', label: 'Money', icon: '💰' },
		{ value: 'email', label: 'Emails', icon: '📧' },
		{ value: 'url', label: 'URLs', icon: '🔗' }
	];

	const languages = [
		{ value: 'en', label: 'English' },
		{ value: 'nl', label: 'Dutch' },
		{ value: 'de', label: 'German' },
		{ value: 'fr', label: 'French' },
		{ value: 'es', label: 'Spanish' },
		{ value: 'it', label: 'Italian' },
		{ value: 'pt', label: 'Portuguese' }
	];

	function getSpeedIcon(speed: string) {
		switch (speed) {
			case 'fast': return '⚡';
			case 'medium': return '🏃';
			case 'slow': return '🐌';
			default: return '❓';
		}
	}

	function getAccuracyIcon(accuracy: string) {
		switch (accuracy) {
			case 'standard': return '✅';
			case 'high': return '🎯';
			case 'research': return '🔬';
			default: return '❓';
		}
	}

	function getCostIcon(cost: string) {
		switch (cost) {
			case 'free': return '🆓';
			case 'low': return '💰';
			case 'medium': return '💰💰';
			case 'high': return '💰💰💰';
			default: return '❓';
		}
	}

	async function saveConfig() {
		loading = true;
		saveStatus = 'saving';
		
		try {
			const response = await fetch('/api/v1/users/entity-config', {
				method: 'PUT',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify(config)
			});

			if (!response.ok) {
				throw new Error('Failed to save configuration');
			}

			saveStatus = 'success';
			setTimeout(() => saveStatus = 'idle', 3000);
		} catch (error) {
			console.error('Failed to save entity config:', error);
			saveStatus = 'error';
			setTimeout(() => saveStatus = 'idle', 5000);
		} finally {
			loading = false;
		}
	}

	onMount(async () => {
		// Load existing configuration
		try {
			const response = await fetch('/api/v1/users/entity-config');
			if (response.ok) {
				const data = await response.json();
				config = { ...config, ...data };
			}
		} catch (error) {
			console.error('Failed to load entity config:', error);
		}
	});

	function toggleEntityType(type: string) {
		if (config.enable_entity_types.includes(type)) {
			config.enable_entity_types = config.enable_entity_types.filter(t => t !== type);
		} else {
			config.enable_entity_types = [...config.enable_entity_types, type];
		}
	}
</script>

<div class="space-y-8">
	<!-- Header -->
	<div class="space-y-2">
		<div class="flex items-center gap-2">
			<h2 class="text-2xl font-bold">Entity Extraction Settings</h2>
			<Badge variant={config.enabled ? "default" : "secondary"}>
				{config.enabled ? "Enabled" : "Disabled"}
			</Badge>
		</div>
		<p class="text-muted-foreground">
			Configure entity recognition to automatically identify persons, organizations, locations, and events in your scraped content.
		</p>
	</div>

	<!-- Enable/Disable Toggle -->
	<Card>
		<CardHeader>
			<div class="flex items-center justify-between">
				<div>
					<CardTitle class="flex items-center gap-2">
						<Zap class="h-5 w-5" />
						Enable Entity Extraction
					</CardTitle>
					<CardDescription>
						Turn on entity recognition for all your scraping projects. This will identify and categorize important entities in your content.
					</CardDescription>
				</div>
				<Switch bind:checked={config.enabled} />
			</div>
		</CardHeader>
	</Card>

	{#if config.enabled}
		<!-- Backend Selection -->
		<Card>
			<CardHeader>
				<CardTitle>Choose Extraction Method</CardTitle>
				<CardDescription>
					Select the entity extraction backend that best fits your needs. Each option has different strengths and trade-offs.
				</CardDescription>
			</CardHeader>
			<CardContent class="space-y-6">
				<div class="grid gap-4">
					{#each backends as backend}
						<div class="border rounded-lg p-4 {config.backend === backend.backend ? 'border-primary bg-primary/5' : 'border-border'}">
							<div class="flex items-start gap-4">
								<div class="flex-shrink-0 mt-1">
									<input 
										type="radio" 
										bind:group={config.backend} 
										value={backend.backend}
										class="h-4 w-4"
									/>
								</div>
								
								<div class="flex-1 space-y-3">
									<!-- Header -->
									<div class="flex items-center justify-between">
										<div>
											<h3 class="font-semibold text-lg">{backend.name}</h3>
											<p class="text-sm text-muted-foreground">{backend.description}</p>
										</div>
										<div class="flex items-center gap-2">
											{#if !backend.available}
												<Badge variant="destructive">Unavailable</Badge>
											{:else}
												<Badge variant="outline">Available</Badge>
											{/if}
										</div>
									</div>

									<!-- Characteristics -->
									<div class="flex items-center gap-6 text-sm">
										<div class="flex items-center gap-1">
											<Clock class="h-4 w-4" />
											<span>Speed: {getSpeedIcon(backend.speed)} {backend.speed}</span>
										</div>
										<div class="flex items-center gap-1">
											<CheckCircle class="h-4 w-4" />
											<span>Accuracy: {getAccuracyIcon(backend.accuracy)} {backend.accuracy}</span>
										</div>
										<div class="flex items-center gap-1">
											<span>Cost: {getCostIcon(backend.cost)} {backend.cost}</span>
										</div>
									</div>

									<!-- Supported Features -->
									<div class="grid grid-cols-2 gap-4 text-xs">
										<div>
											<div class="font-medium text-muted-foreground mb-1">Languages:</div>
											<div class="flex flex-wrap gap-1">
												{#each backend.supported_languages.slice(0, 3) as lang}
													<Badge variant="outline" class="text-xs">{lang}</Badge>
												{/each}
												{#if backend.supported_languages.length > 3}
													<Badge variant="outline" class="text-xs">+{backend.supported_languages.length - 3}</Badge>
												{/if}
											</div>
										</div>
										<div>
											<div class="font-medium text-muted-foreground mb-1">Entity Types:</div>
											<div class="flex flex-wrap gap-1">
												{#each backend.entity_types.slice(0, 4) as type}
													<Badge variant="outline" class="text-xs">{type}</Badge>
												{/each}
												{#if backend.entity_types.length > 4}
													<Badge variant="outline" class="text-xs">+{backend.entity_types.length - 4}</Badge>
												{/if}
											</div>
										</div>
									</div>

									<!-- Pros and Cons -->
									<Tabs defaultValue="pros" class="w-full">
										<TabsList class="grid w-full grid-cols-2">
											<TabsTrigger value="pros">Advantages</TabsTrigger>
											<TabsTrigger value="cons">Limitations</TabsTrigger>
										</TabsList>
										<TabsContent value="pros" class="space-y-1">
											{#each backend.pros as pro}
												<div class="text-sm flex items-start gap-2">
													<span class="text-green-600 mt-0.5">•</span>
													<span>{pro}</span>
												</div>
											{/each}
										</TabsContent>
										<TabsContent value="cons" class="space-y-1">
											{#each backend.cons as con}
												<div class="text-sm flex items-start gap-2">
													<span class="text-red-600 mt-0.5">•</span>
													<span>{con}</span>
												</div>
											{/each}
										</TabsContent>
									</Tabs>

									<!-- Backend-specific Configuration -->
									{#if config.backend === backend.backend && backend.config_schema}
										<div class="border-t pt-3 space-y-3">
											<h4 class="font-medium text-sm">Configuration</h4>
											{#if backend.backend === 'firecrawl_extraction'}
												<div class="grid gap-3">
													<div>
														<Label for="firecrawl_url">Firecrawl Service URL</Label>
														<Input 
															id="firecrawl_url"
															bind:value={config.backend_config.firecrawl_url}
															placeholder="http://localhost:3002"
															class="text-sm"
														/>
													</div>
													<div>
														<Label for="extraction_timeout">Extraction Timeout (seconds)</Label>
														<Input 
															id="extraction_timeout"
															type="number"
															bind:value={config.backend_config.extraction_timeout}
															placeholder="30"
															class="text-sm"
														/>
													</div>
												</div>
											{/if}
										</div>
									{/if}
								</div>
							</div>
						</div>
					{/each}
				</div>
			</CardContent>
		</Card>

		<!-- Language and Entity Type Settings -->
		<div class="grid gap-6 md:grid-cols-2">
			<!-- Language Settings -->
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Globe class="h-5 w-5" />
						Language Settings
					</CardTitle>
					<CardDescription>
						Configure primary language for entity extraction
					</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					<div>
						<Label for="primary_language">Primary Language</Label>
						<Select bind:value={config.language}>
							<SelectTrigger>
								<SelectValue placeholder="Select language" />
							</SelectTrigger>
							<SelectContent>
								{#each languages.filter(l => selectedBackend?.supported_languages.includes(l.value)) as lang}
									<SelectItem value={lang.value}>{lang.label}</SelectItem>
								{/each}
							</SelectContent>
						</Select>
					</div>
				</CardContent>
			</Card>

			<!-- Wikidata Enrichment -->
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Info class="h-5 w-5" />
						Wikidata Enrichment
					</CardTitle>
					<CardDescription>
						Enhance entities with additional information from Wikidata
					</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="flex items-center justify-between">
						<Label for="enable_wikidata">Enable Wikidata enrichment</Label>
						<Switch bind:checked={config.enable_wikidata} id="enable_wikidata" />
					</div>
					
					{#if config.enable_wikidata}
						<div>
							<Label for="wikidata_language">Wikidata Content Language</Label>
							<Select bind:value={config.wikidata_language}>
								<SelectTrigger>
									<SelectValue placeholder="Select language" />
								</SelectTrigger>
								<SelectContent>
									{#each languages as lang}
										<SelectItem value={lang.value}>{lang.label}</SelectItem>
									{/each}
								</SelectContent>
							</Select>
						</div>
					{/if}
				</CardContent>
			</Card>
		</div>

		<!-- Entity Types -->
		<Card>
			<CardHeader>
				<CardTitle>Entity Types to Extract</CardTitle>
				<CardDescription>
					Select which types of entities you want to identify and extract from your content.
				</CardDescription>
			</CardHeader>
			<CardContent>
				<div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
					{#each entityTypes.filter(et => selectedBackend?.entity_types.includes(et.value)) as entityType}
						<div class="flex items-center space-x-2">
							<Checkbox 
								id={entityType.value}
								checked={config.enable_entity_types.includes(entityType.value)}
								onCheckedChange={() => toggleEntityType(entityType.value)}
							/>
							<Label for={entityType.value} class="flex items-center gap-2 cursor-pointer">
								<span>{entityType.icon}</span>
								<span>{entityType.label}</span>
							</Label>
						</div>
					{/each}
				</div>
			</CardContent>
		</Card>

		<!-- Advanced Settings -->
		<Card>
			<CardHeader>
				<CardTitle>Advanced Settings</CardTitle>
				<CardDescription>
					Fine-tune entity extraction performance and quality settings
				</CardDescription>
			</CardHeader>
			<CardContent class="space-y-4">
				<div class="grid gap-4 md:grid-cols-2">
					<div>
						<Label for="confidence_threshold">
							Confidence Threshold: {config.confidence_threshold}
						</Label>
						<input
							id="confidence_threshold"
							type="range"
							min="0.1"
							max="1.0"
							step="0.1"
							bind:value={config.confidence_threshold}
							class="w-full"
						/>
						<div class="text-xs text-muted-foreground mt-1">
							Only extract entities with confidence above this threshold
						</div>
					</div>
					
					<div>
						<Label for="max_entities">Max Entities per Page</Label>
						<Input 
							id="max_entities"
							type="number"
							bind:value={config.max_entities_per_page}
							min="10"
							max="500"
						/>
					</div>
				</div>
				
				<div class="flex items-center justify-between">
					<div>
						<Label for="context_extraction">Extract Context Around Entities</Label>
						<div class="text-xs text-muted-foreground">
							Include surrounding text for better entity understanding
						</div>
					</div>
					<Switch bind:checked={config.enable_context_extraction} id="context_extraction" />
				</div>
			</CardContent>
		</Card>

		<!-- Save Button -->
		<div class="flex items-center justify-between">
			<div>
				{#if saveStatus === 'success'}
					<Alert class="w-fit">
						<CheckCircle class="h-4 w-4" />
						<AlertDescription>Settings saved successfully!</AlertDescription>
					</Alert>
				{:else if saveStatus === 'error'}
					<Alert variant="destructive" class="w-fit">
						<AlertCircle class="h-4 w-4" />
						<AlertDescription>Failed to save settings. Please try again.</AlertDescription>
					</Alert>
				{/if}
			</div>
			
			<Button 
				onclick={saveConfig} 
				disabled={loading}
				class="min-w-[100px]"
			>
				{#if loading}
					Saving...
				{:else}
					Save Settings
				{/if}
			</Button>
		</div>
	{/if}
</div>