/**
 * These tests require a running Hindsight API server.
 */

import { HindsightClient } from '../src';

// Test configuration
const HINDSIGHT_API_URL = process.env.HINDSIGHT_API_URL || 'http://localhost:8888';
const TEST_BANK_ID = `test_bank_${new Date().toISOString().replace(/[-:T.Z]/g, '').slice(0, 15)}`;

let client: HindsightClient;

beforeAll(() => {
    client = new HindsightClient({ baseUrl: HINDSIGHT_API_URL });
});

describe('TestRetain', () => {
    test('retain single memory', async () => {
        const response = await client.retain(
            TEST_BANK_ID,
            'Alice loves artificial intelligence and machine learning'
        );

        expect(response).not.toBeNull();
        expect(response.success).toBe(true);
        expect(response.items_count).toBe(1);
    });

    test('retain memory with context', async () => {
        const response = await client.retain(TEST_BANK_ID, 'Bob went hiking in the mountains', {
            timestamp: new Date('2024-01-15T10:30:00'),
            context: 'outdoor activities',
        });

        expect(response).not.toBeNull();
        expect(response.success).toBe(true);
    });

    test('retain batch memories', async () => {
        const response = await client.retainBatch(TEST_BANK_ID, [
            { content: 'Charlie enjoys reading science fiction books' },
            { content: 'Diana is learning to play the guitar', context: 'hobbies' },
            { content: 'Eve completed a marathon last month', timestamp: '2024-10-15' },
        ]);

        expect(response).not.toBeNull();
        expect(response.success).toBe(true);
        expect(response.items_count).toBe(3);
    });
});

describe('TestRecall', () => {
    beforeAll(async () => {
        // Setup: Store some test memories before recall tests
        await client.retainBatch(TEST_BANK_ID, [
            { content: 'Alice loves programming in Python' },
            { content: 'Bob enjoys hiking and outdoor adventures' },
            { content: 'Charlie is interested in quantum physics' },
            { content: 'Diana plays the violin beautifully' },
        ]);
    });

    test('recall basic', async () => {
        const response = await client.recall(TEST_BANK_ID, 'What does Alice like?');

        expect(response).not.toBeNull();
        expect(response.results).toBeDefined();
        expect(response.results!.length).toBeGreaterThan(0);

        // Check that at least one result contains relevant information
        const resultTexts = response.results!.map((r) => r.text || '');
        const hasRelevant = resultTexts.some(
            (text: string) => text.includes('Alice') || text.includes('Python') || text.includes('programming')
        );
        expect(hasRelevant).toBe(true);
    });

    test('recall with max tokens', async () => {
        const response = await client.recall(TEST_BANK_ID, 'outdoor activities', {
            maxTokens: 1024,
        });

        expect(response).not.toBeNull();
        expect(response.results).toBeDefined();
        expect(Array.isArray(response.results)).toBe(true);
    });

    test('recall with types filter', async () => {
        const response = await client.recall(TEST_BANK_ID, "What are people's hobbies?", {
            types: ['world'],
            maxTokens: 2048,
            trace: true,
        });

        expect(response).not.toBeNull();
        expect(response.results).toBeDefined();
        // Trace should be included when enabled
        if (response.trace) {
            expect(typeof response.trace).toBe('object');
        }
    });
});

describe('TestReflect', () => {
    beforeAll(async () => {
        // Setup: Create bank and store test memories
        await client.createBank(TEST_BANK_ID, {
            name: 'Test Bank',
            background: 'I am a helpful AI assistant interested in technology and science.',
        });

        await client.retainBatch(TEST_BANK_ID, [
            { content: 'The Python programming language is great for data science' },
            { content: 'Machine learning models can recognize patterns in data' },
            { content: 'Neural networks are inspired by biological neurons' },
        ]);
    });

    test('reflect basic', async () => {
        const response = await client.reflect(
            TEST_BANK_ID,
            'What do you think about artificial intelligence?'
        );

        expect(response).not.toBeNull();
        expect(response.text).toBeDefined();
        expect(response.text!.length).toBeGreaterThan(0);

        // Should include facts that were used
        if (response.based_on) {
            expect(Array.isArray(response.based_on)).toBe(true);
        }
    });

    test('reflect with context', async () => {
        const response = await client.reflect(TEST_BANK_ID, 'Should I learn Python?', {
            context: "I'm interested in starting a career in data science",
            budget: 'low',
        });

        expect(response).not.toBeNull();
        expect(response.text).toBeDefined();
        expect(response.text!.length).toBeGreaterThan(0);
    });
});

describe('TestListMemories', () => {
    beforeAll(async () => {
        // Setup: Store some test memories
        await client.retainBatch(TEST_BANK_ID, [
            { content: 'Test memory 0' },
            { content: 'Test memory 1' },
            { content: 'Test memory 2' },
            { content: 'Test memory 3' },
            { content: 'Test memory 4' },
        ]);
    });

    test('list all memories', async () => {
        const response = await client.listMemories(TEST_BANK_ID);

        expect(response).not.toBeNull();
        expect(response.items).toBeDefined();
        expect(response.total).toBeDefined();
        expect(response.items!.length).toBeGreaterThan(0);
    });

    test('list with pagination', async () => {
        const response = await client.listMemories(TEST_BANK_ID, {
            limit: 2,
            offset: 0,
        });

        expect(response).not.toBeNull();
        expect(response.items).toBeDefined();
        expect(response.items!.length).toBeLessThanOrEqual(2);
    });
});

describe('TestEndToEndWorkflow', () => {
    test('complete workflow', async () => {
        const workflowBankId = `workflow_test_${new Date().toISOString().replace(/[-:T.Z]/g, '').slice(0, 15)}`;

        // 1. Create bank
        await client.createBank(workflowBankId, {
            name: 'Alice',
            background: 'I am a software engineer who loves Python programming.',
        });

        // 2. Store memories
        const retainResponse = await client.retainBatch(workflowBankId, [
            { content: 'I completed a project using FastAPI' },
            { content: 'I learned about async programming in Python' },
            { content: 'I enjoy working on open source projects' },
        ]);
        expect(retainResponse.success).toBe(true);

        // 3. Search for relevant memories
        const recallResponse = await client.recall(
            workflowBankId,
            'What programming technologies do I use?'
        );
        expect(recallResponse.results!.length).toBeGreaterThan(0);

        // 4. Generate contextual answer
        const reflectResponse = await client.reflect(
            workflowBankId,
            'What are my professional interests?'
        );
        expect(reflectResponse.text).toBeDefined();
        expect(reflectResponse.text!.length).toBeGreaterThan(0);
    });
});
