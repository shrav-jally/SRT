This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

### Login Flow

1. The redirection happens server side using `ui/src/stack.tsx` after the user has logged in.

### Sentry and PostHog

1. Initialized in `ui/src/instrumentation-client.ts`
