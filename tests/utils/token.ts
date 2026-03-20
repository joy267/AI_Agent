import fs from 'fs';
import userjson from '../../user.json'

export function getRefreshToken(): string {
  const rawData = fs.readFileSync('user.json', 'utf-8');
  const storageState = JSON.parse(rawData);

  const refreshToken = storageState.cookies?.find(
    (cookie: any) => cookie.name === 'refresh_token'
  )?.value;

  if (!refreshToken) {
    throw new Error('refresh_token not found in user.json');
  }

  return refreshToken;
}
