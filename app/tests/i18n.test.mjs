import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { createInstance } from 'i18next';
import { en, ru } from '../src/i18n/catalog.ts';
import { publicMessagesRu } from '../src/i18n/publicMessages.ts';
import { messageText, statusText } from '../src/i18n/messages.ts';

async function translator(language) {
  const instance = createInstance();
  await instance.init({ lng: language, fallbackLng: 'en', defaultNS: 'translation', interpolation: { escapeValue: false },
    resources: { en: { translation: en, messages: Object.fromEntries(Object.keys(publicMessagesRu).map(key => [key, key])) },
      ru: { translation: ru, messages: publicMessagesRu } } });
  return instance;
}
const placeholders = value => [...value.matchAll(/\{\{(\w+)\}\}/g)].map(match => match[1]).sort();

test('Russian copy covers every interface key and retains interpolated values', () => {
  assert.deepEqual(Object.keys(ru).sort(), Object.keys(en).sort());
  for (const [key, value] of Object.entries(ru)) {
    assert.match(value, /[А-Яа-яЁё]/, key);
    if (!['unrecognizedMessage', 'unrecognizedErrorCode'].includes(key)) {
      assert.deepEqual(placeholders(value), placeholders(en[key]), key);
    }
  }
  for (const [english, russian] of Object.entries(publicMessagesRu)) {
    assert.match(russian, /[А-Яа-яЁё]/, english);
    assert.deepEqual(placeholders(russian), placeholders(english), english);
  }
});

test('all page and component copy uses existing translation keys', () => {
  const directory = fileURLToPath(new URL('../src/', import.meta.url));
  for (const area of ['pages', 'components']) {
    for (const filename of readdirSync(`${directory}/${area}`).filter(name => name.endsWith('.tsx'))) {
      const path = `${directory}/${area}/${filename}`;
      const source = ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
      function visit(node) {
        if (ts.isJsxText(node) && /[A-Za-zА-Яа-яЁё]/.test(node.text)) {
          assert.equal(node.text.trim(), 'Kedrogy', `${filename}: untranslated JSX text`);
        }
        if (ts.isJsxAttribute(node) && ['title', 'placeholder', 'aria-label'].includes(node.name.getText(source)) && node.initializer) {
          assert.ok(!ts.isStringLiteral(node.initializer), `${filename}: untranslated ${node.name.getText(source)}`);
        }
        if (ts.isCallExpression(node) && node.expression.getText(source) === 't') {
          function checkKey(key) {
            if (ts.isStringLiteral(key)) assert.ok(Object.hasOwn(en, key.text), `${filename}: missing ${key.text}`);
            else if (ts.isConditionalExpression(key)) { checkKey(key.whenTrue); checkKey(key.whenFalse); }
          }
          checkKey(node.arguments[0]);
        }
        ts.forEachChild(node, visit);
      }
      visit(source);
    }
  }
});

test('domain statuses and dynamic task titles render in Russian and switch back', async () => {
  const instance = await translator('ru');
  for (const status of ['READY', 'QUEUED', 'RUNNING', 'VERIFYING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT',
    'INTERRUPTED', 'RETRY_WAIT', 'NEEDS_REVIEW', 'UNVERIFIED', 'STARTING', 'UNAVAILABLE', 'STOPPING',
    'STOPPED', 'UNKNOWN', 'EMPTY', 'PRESENT', 'INVALID', 'PENDING', 'BOUND', 'UNRESOLVED', 'VERIFIED', 'MISSING']) {
    assert.match(statusText(status, instance.t), /[А-Яа-яЁё]/, status);
  }
  assert.equal(instance.t('trainingTitle', { id: 21 }), 'Обучение модели №21');
  assert.equal(statusText('UNRECOGNIZED', instance.t), 'Неизвестный статус');
  await instance.changeLanguage('en');
  assert.equal(instance.t('trainingTitle', { id: 21 }), 'Training model #21');
  assert.equal(statusText('READY', instance.t), 'Ready');
});

test('public errors, field validation and cleanup diagnostics retain specific details', async () => {
  const instance = await translator('ru');
  assert.equal(messageText('Ownership is unresolved for Deployment/serve-20.', instance.t), 'Не установлена принадлежность ресурса Deployment/serve-20.');
  assert.equal(messageText('Request failed (HTTP 503).', instance.t), 'Ошибка запроса (HTTP 503).');
  assert.equal(messageText('dataset_name: This setting is required. labels: Every label must be a string.', instance.t), 'Название: Это поле обязательно. Метки: Каждая метка должна быть строкой.');
  assert.equal(messageText('Removing model-21', instance.t), 'Удаление ресурса model-21');
  assert.equal(messageText('Annotation validation failed: 2 invalid and 3 conflicting records. Review policy, source identity and explicit choices.', instance.t),
    'Проверка разметки не пройдена: некорректных записей — 2, противоречивых — 3. Проверьте правила, источник и выбранные классы.');
  assert.match(messageText('Unknown upstream failure', instance.t, 'UPSTREAM_ERROR'), /Ошибка операции \(UPSTREAM_ERROR\)/);
  assert.equal(messageText('', instance.t), '');
  const message = 'The prediction request timed out.';
  assert.equal(messageText(message, instance.t), 'Истекло время ожидания предсказания.');
  await instance.changeLanguage('en');
  assert.equal(messageText(message, instance.t), message);
});

test('language persists across initialization and sets the document language', async () => {
  const storage = new Map([['kedrogy.language', 'ru']]);
  const oldStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const oldDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value),
  } });
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { documentElement: { lang: '' } } });
  try {
    const { default: instance, savedLanguage } = await import('../src/i18n/config.ts');
    assert.equal(instance.resolvedLanguage, 'ru');
    assert.equal(document.documentElement.lang, 'ru');
    await instance.changeLanguage('en');
    assert.equal(storage.get('kedrogy.language'), 'en');
    assert.equal(savedLanguage(), 'en');
    assert.equal(document.documentElement.lang, 'en');
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('Storage blocked'); } });
    await instance.changeLanguage('ru');
    assert.equal(document.documentElement.lang, 'ru');
    assert.doesNotThrow(() => savedLanguage());
  } finally {
    if (oldStorage) Object.defineProperty(globalThis, 'localStorage', oldStorage); else delete globalThis.localStorage;
    if (oldDocument) Object.defineProperty(globalThis, 'document', oldDocument); else delete globalThis.document;
  }
});
