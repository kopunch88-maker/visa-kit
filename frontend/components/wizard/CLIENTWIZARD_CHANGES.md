# Pack 13.1 — изменения в ClientWizard.tsx

В файле `D:\VISA\visa_kit\frontend\components\wizard\ClientWizard.tsx`
нужно сделать **одно небольшое изменение**.

## Что меняется

После того как клиент применил распознанные данные в Шаге 0 и переходит на Шаг 1,
**в state ClientWizard'а данные ещё старые** (без OCR-полей). Нужно перезагрузить
их из backend.

## Найди функцию `handleDocumentsContinue`

Она выглядит сейчас так:

```typescript
function handleDocumentsContinue() {
    setCompletedSteps((prev) => new Set([...prev, 0]));
    setMaxReachedStep((prev) => Math.max(prev, 1));
    setCurrentStep(1);
    scrollToStep(1);
}
```

## Замени её на:

```typescript
async function handleDocumentsContinue() {
    setCompletedSteps((prev) => new Set([...prev, 0]));
    setMaxReachedStep((prev) => Math.max(prev, 1));

    // Pack 13.1: перезагружаем профиль после возможного применения OCR данных
    try {
      const profile = await getMyProfile(token);
      if (profile) {
        setData(profile);
        // Помечаем шаги как завершённые если данные подгрузились
        const completed = new Set<number>([0]);
        if (profile.last_name_native && profile.first_name_native) completed.add(1);
        if (profile.passport_number) completed.add(2);
        if (profile.home_address && profile.email) completed.add(3);
        if (profile.education && profile.education.length > 0) completed.add(4);
        if (profile.work_history && profile.work_history.length > 0) completed.add(5);
        setCompletedSteps(completed);
        const maxCompleted = Math.max(...Array.from(completed));
        setMaxReachedStep(Math.min(maxCompleted + 1, STEPS.length - 1));
      }
    } catch (e) {
      console.error("Failed to reload profile:", e);
    }

    setCurrentStep(1);
    scrollToStep(1);
}
```

## Что именно изменилось

- Функция стала `async`
- После переключения шага вызываем `getMyProfile` чтобы подгрузить свежие данные
- Если в profile появились новые поля (например `last_name_native` после OCR паспорта) —
  соответствующие шаги отметятся как `completed` (галочка в sidebar)
- `maxReachedStep` обновляется чтобы клиент мог скакать по уже заполненным шагам

## Всё остальное в ClientWizard.tsx — БЕЗ изменений
