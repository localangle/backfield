#!/usr/bin/env node

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Try different paths for local vs Docker environments
const possiblePaths = [
  path.join(__dirname, '../../../packages/backfield-core/src/backfield_core/nodes'),
  path.join(__dirname, '../packages/backfield-core/src/backfield_core/nodes'),
  '/app/packages/backfield-core/src/backfield_core/nodes',
];

let NODES_SOURCE_DIR = null;
for (const testPath of possiblePaths) {
  if (fs.existsSync(testPath)) {
    NODES_SOURCE_DIR = testPath;
    break;
  }
}

if (!NODES_SOURCE_DIR) {
  console.error('Could not find backfield_core/nodes. Tried paths:', possiblePaths);
  process.exit(1);
}
const NODES_TARGET_DIR = path.join(__dirname, '../src/nodes');
const REGISTRY_FILE = path.join(NODES_TARGET_DIR, 'registry.ts');

// Ensure target directory exists
if (!fs.existsSync(NODES_TARGET_DIR)) {
  fs.mkdirSync(NODES_TARGET_DIR, { recursive: true });
}

// Scan for node folders
console.log(`Scanning directory: ${NODES_SOURCE_DIR}`);
console.log(`Directory exists: ${fs.existsSync(NODES_SOURCE_DIR)}`);

const nodeFolders = fs.readdirSync(NODES_SOURCE_DIR, { withFileTypes: true })
  .filter(dirent => dirent.isDirectory() && dirent.name !== '__pycache__')
  .map(dirent => dirent.name);

console.log(`Found node folders: ${nodeFolders.join(', ')}`);

const nodeMetadata = [];
const nodeComponents = {};
const panelComponents = {};
const visualizationComponents = {};

// Process each node folder
for (const nodeFolder of nodeFolders) {
  const nodePath = path.join(NODES_SOURCE_DIR, nodeFolder);
  const metadataPath = path.join(nodePath, 'metadata.json');
  const uiPath = path.join(nodePath, 'ui');
  
  // Check if metadata.json exists
  if (!fs.existsSync(metadataPath)) {
    console.log(`Skipping ${nodeFolder}: no metadata.json found`);
    continue;
  }
  
  // Read metadata
  const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));

  // If metadata has a prompt_file in defaultParams, load it and populate the prompt field
  if (metadata.defaultParams && metadata.defaultParams.prompt_file) {
    const promptFilePath = metadata.defaultParams.prompt_file;
    // Resolve path relative to the node directory
    const fullPromptPath = path.isAbsolute(promptFilePath) 
      ? promptFilePath 
      : path.join(nodePath, promptFilePath);
    
    try {
      if (fs.existsSync(fullPromptPath)) {
        const promptContent = fs.readFileSync(fullPromptPath, 'utf8');
        // Only populate if prompt is empty or not set
        if (!metadata.defaultParams.prompt || metadata.defaultParams.prompt === '') {
          metadata.defaultParams.prompt = promptContent;
        }
      } else {
        console.log(`Warning: Prompt file not found for ${nodeFolder}: ${fullPromptPath}`);
      }
    } catch (error) {
      console.log(`Warning: Failed to load prompt file for ${nodeFolder}: ${error.message}`);
    }
  }
  
  // If metadata has an output_format_file in defaultParams, load it and populate the output_format field
  if (metadata.defaultParams && metadata.defaultParams.output_format_file) {
    const outputFormatFilePath = metadata.defaultParams.output_format_file;
    // Resolve path relative to the node directory
    const fullOutputFormatPath = path.isAbsolute(outputFormatFilePath) 
      ? outputFormatFilePath 
      : path.join(nodePath, outputFormatFilePath);
    
    try {
      if (fs.existsSync(fullOutputFormatPath)) {
        const outputFormatContent = fs.readFileSync(fullOutputFormatPath, 'utf8');
        // Add output_format to defaultParams
        metadata.defaultParams.output_format = outputFormatContent;
      } else {
        console.log(`Warning: Output format file not found for ${nodeFolder}: ${fullOutputFormatPath}`);
      }
    } catch (error) {
      console.log(`Warning: Failed to load output format file for ${nodeFolder}: ${error.message}`);
    }
  }
  
  nodeMetadata.push(metadata);
  
  // Create target directory for this node
  const targetNodeDir = path.join(NODES_TARGET_DIR, nodeFolder);
  if (!fs.existsSync(targetNodeDir)) {
    fs.mkdirSync(targetNodeDir, { recursive: true });
  }
  
  // Copy UI components if they exist
  const nodeComponentPath = path.join(uiPath, 'NodeComponent.tsx');
  const panelComponentPath = path.join(uiPath, 'PanelComponent.tsx');
  const visualizationComponentPath = path.join(uiPath, 'VisualizationComponent.tsx');
  
  if (fs.existsSync(nodeComponentPath)) {
    const targetNodeComponent = path.join(targetNodeDir, 'NodeComponent.tsx');
    
    // Read the original component
    let componentContent = fs.readFileSync(nodeComponentPath, 'utf8');
    
    const hasMetadata = /const\s+nodeMetadata\s*=/.test(componentContent) || /Auto-injected metadata/.test(componentContent);
    if (!hasMetadata) {
      // Inject metadata after the first import statement
      const metadataImport = `// Auto-injected metadata for ${metadata.type}
const nodeMetadata = ${JSON.stringify(metadata, null, 2)};

`;
      const importMatch = componentContent.match(/^import.*?from.*?;$/m);
      if (importMatch) {
        const insertIndex = importMatch.index + importMatch[0].length;
        componentContent = componentContent.slice(0, insertIndex) + '\n' + metadataImport + componentContent.slice(insertIndex);
      } else {
        // If no imports found, add at the beginning
        componentContent = metadataImport + componentContent;
      }
    }
    
    // Write the modified component
    fs.writeFileSync(targetNodeComponent, componentContent);
    console.log(`Copied NodeComponent for ${metadata.type}`);
    
    // Add to nodeComponents
    nodeComponents[metadata.type] = `lazy(() => import('./${nodeFolder}/NodeComponent'))`;
  }
  
  if (fs.existsSync(panelComponentPath)) {
    const targetPanelComponent = path.join(targetNodeDir, 'PanelComponent.tsx');
    
    // Read the original component
    let componentContent = fs.readFileSync(panelComponentPath, 'utf8');
    
    const hasMetadata = /const\s+nodeMetadata\s*=/.test(componentContent) || /Auto-injected metadata/.test(componentContent);
    if (!hasMetadata) {
      // Inject metadata after the first import statement
      const metadataImport = `// Auto-injected metadata for ${metadata.type}
const nodeMetadata = ${JSON.stringify(metadata, null, 2)};

`;
      const importMatch = componentContent.match(/^import.*?from.*?;$/m);
      if (importMatch) {
        const insertIndex = importMatch.index + importMatch[0].length;
        componentContent = componentContent.slice(0, insertIndex) + '\n' + metadataImport + componentContent.slice(insertIndex);
      } else {
        // If no imports found, add at the beginning
        componentContent = metadataImport + componentContent;
      }
    }
    
    // Write the modified component
    fs.writeFileSync(targetPanelComponent, componentContent);
    console.log(`Copied PanelComponent for ${metadata.type}`);
    
    // Add to panelComponents
    panelComponents[metadata.type] = `lazy(() => import('./${nodeFolder}/PanelComponent'))`;
  }
  
  if (fs.existsSync(visualizationComponentPath)) {
    const targetVisualizationComponent = path.join(targetNodeDir, 'VisualizationComponent.tsx');
    
    // Read the original component
    let componentContent = fs.readFileSync(visualizationComponentPath, 'utf8');
    
    const hasMetadata = /const\s+nodeMetadata\s*=/.test(componentContent) || /Auto-injected metadata/.test(componentContent);
    if (!hasMetadata) {
      // Inject metadata after the first import statement
      const metadataImport = `// Auto-injected metadata for ${metadata.type}
const nodeMetadata = ${JSON.stringify(metadata, null, 2)};

`;
      const importMatch = componentContent.match(/^import.*?from.*?;$/m);
      if (importMatch) {
        const insertIndex = importMatch.index + importMatch[0].length;
        componentContent = componentContent.slice(0, insertIndex) + '\n' + metadataImport + componentContent.slice(insertIndex);
      } else {
        // If no imports found, add at the beginning
        componentContent = metadataImport + componentContent;
      }
    }
    
    // Write the modified component
    fs.writeFileSync(targetVisualizationComponent, componentContent);
    console.log(`Copied VisualizationComponent for ${metadata.type}`);
    
    // Add to visualizationComponents
    visualizationComponents[metadata.type] = `() => import('./${nodeFolder}/VisualizationComponent')`;
  }
}

// Generate registry.ts
const registryContent = `// Auto-generated by sync-nodes.js - DO NOT EDIT MANUALLY
import { lazy } from 'react';

export const nodeMetadata = ${JSON.stringify(nodeMetadata, null, 2)};

export const nodeComponents = {
${Object.entries(nodeComponents).map(([type, importPath]) => `  ${type}: ${importPath},`).join('\n')}
};

export const panelComponents = {
${Object.entries(panelComponents).map(([type, importPath]) => `  ${type}: ${importPath},`).join('\n')}
};

export const visualizationComponents = {
${Object.entries(visualizationComponents).map(([type, importPath]) => `  ${type}: ${importPath},`).join('\n')}
};

export type NodeType = keyof typeof nodeComponents;
export type PanelType = keyof typeof panelComponents;
export type VisualizationType = keyof typeof visualizationComponents;
`;

fs.writeFileSync(REGISTRY_FILE, registryContent);
console.log(`Generated registry.ts with ${nodeMetadata.length} nodes`);
