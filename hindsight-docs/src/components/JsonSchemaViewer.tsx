import React, {useState} from 'react';

/**
 * Renders a JSON Schema as an interactive, collapsible property tree.
 * Designed for Pydantic-generated schemas with $defs references.
 */

interface SchemaNode {
  type?: string;
  description?: string;
  title?: string;
  properties?: Record<string, SchemaNode>;
  required?: string[];
  items?: SchemaNode;
  anyOf?: SchemaNode[];
  allOf?: SchemaNode[];
  $ref?: string;
  default?: unknown;
  enum?: unknown[];
  const?: unknown;
  minimum?: number;
  maximum?: number;
  $defs?: Record<string, SchemaNode>;
  // Pydantic extras
  examples?: unknown[];
}

interface Props {
  schema: SchemaNode;
}

function resolveRef(ref: string, root: SchemaNode): SchemaNode | undefined {
  // Handle "#/$defs/Foo" style refs
  const parts = ref.replace('#/', '').split('/');
  let node: unknown = root;
  for (const part of parts) {
    if (node && typeof node === 'object' && part in node) {
      node = (node as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return node as SchemaNode;
}

function resolveType(schema: SchemaNode, root: SchemaNode): {typeName: string; resolved: SchemaNode} {
  if (schema.$ref) {
    const resolved = resolveRef(schema.$ref, root);
    if (resolved) {
      const name = schema.$ref.split('/').pop() || 'object';
      return {typeName: name, resolved};
    }
    return {typeName: 'unknown', resolved: schema};
  }

  // Handle anyOf (Pydantic's way of expressing Optional[T])
  if (schema.anyOf) {
    const nonNull = schema.anyOf.filter(
      (s) => !(s.type === 'null') && !(s.const === null),
    );
    if (nonNull.length === 1) {
      const inner = resolveType(nonNull[0], root);
      return {typeName: inner.typeName + ' | null', resolved: inner.resolved};
    }
    const names = nonNull.map((s) => resolveType(s, root).typeName);
    return {typeName: names.join(' | '), resolved: schema};
  }

  if (schema.items) {
    const inner = resolveType(schema.items, root);
    return {typeName: `${inner.typeName}[]`, resolved: schema};
  }

  return {typeName: schema.type || 'object', resolved: schema};
}

function PropertyRow({
  name,
  schema,
  root,
  required,
  depth,
}: {
  name: string;
  schema: SchemaNode;
  root: SchemaNode;
  required: boolean;
  depth: number;
}) {
  const {typeName, resolved} = resolveType(schema, root);
  const hasChildren = resolved.properties && Object.keys(resolved.properties).length > 0;
  const [expanded, setExpanded] = useState(depth < 1);

  const description = schema.description || resolved.description || '';
  const hasDefault = 'default' in schema && schema.default !== undefined;

  return (
    <>
      <tr>
        <td style={{paddingLeft: `${depth * 1.2 + 0.5}rem`, whiteSpace: 'nowrap'}}>
          {hasChildren ? (
            <button
              onClick={() => setExpanded(!expanded)}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
                marginRight: '0.3rem',
                fontSize: '0.7rem',
                color: 'var(--ifm-color-emphasis-500)',
              }}>
              {expanded ? '\u25BC' : '\u25B6'}
            </button>
          ) : (
            <span style={{display: 'inline-block', width: '1rem'}} />
          )}
          <code style={{fontSize: '0.85rem'}}>{name}</code>
        </td>
        <td>
          <code style={{fontSize: '0.8rem', color: 'var(--ifm-color-primary)'}}>{typeName}</code>
        </td>
        <td>
          {required ? (
            <span
              style={{
                fontSize: '0.65rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                background: 'rgba(255, 100, 100, 0.12)',
                color: '#d44',
                padding: '0.1rem 0.4rem',
                borderRadius: '4px',
              }}>
              required
            </span>
          ) : hasDefault ? (
            <code style={{fontSize: '0.75rem', color: 'var(--ifm-color-emphasis-500)'}}>
              {JSON.stringify(schema.default)}
            </code>
          ) : (
            <span style={{color: 'var(--ifm-color-emphasis-400)', fontSize: '0.8rem'}}>-</span>
          )}
        </td>
        <td style={{fontSize: '0.83rem', color: 'var(--ifm-color-emphasis-700)'}}>
          {description}
          {schema.enum && (
            <span style={{marginLeft: '0.3rem', fontSize: '0.75rem', color: 'var(--ifm-color-emphasis-500)'}}>
              Enum: {schema.enum.map((v) => JSON.stringify(v)).join(', ')}
            </span>
          )}
          {schema.minimum !== undefined && (
            <span style={{marginLeft: '0.3rem', fontSize: '0.75rem', color: 'var(--ifm-color-emphasis-500)'}}>
              (min: {schema.minimum})
            </span>
          )}
          {schema.maximum !== undefined && (
            <span style={{marginLeft: '0.3rem', fontSize: '0.75rem', color: 'var(--ifm-color-emphasis-500)'}}>
              (max: {schema.maximum})
            </span>
          )}
        </td>
      </tr>
      {hasChildren &&
        expanded &&
        Object.entries(resolved.properties!).map(([childName, childSchema]) => (
          <PropertyRow
            key={`${name}.${childName}`}
            name={childName}
            schema={childSchema}
            root={root}
            required={resolved.required?.includes(childName) ?? false}
            depth={depth + 1}
          />
        ))}
    </>
  );
}

export default function JsonSchemaViewer({schema}: Props): React.ReactElement {
  if (!schema.properties) {
    return <pre>{JSON.stringify(schema, null, 2)}</pre>;
  }

  return (
    <div style={{overflowX: 'auto'}}>
      <table style={{width: '100%', fontSize: '0.9rem'}}>
        <thead>
          <tr>
            <th style={{width: '25%'}}>Property</th>
            <th style={{width: '15%'}}>Type</th>
            <th style={{width: '15%'}}>Required / Default</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(schema.properties).map(([name, propSchema]) => (
            <PropertyRow
              key={name}
              name={name}
              schema={propSchema}
              root={schema}
              required={schema.required?.includes(name) ?? false}
              depth={0}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
