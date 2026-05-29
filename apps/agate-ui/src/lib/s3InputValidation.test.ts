import { describe, expect, it } from 'vitest'
import {
  isValidS3BucketName,
  normalizeS3BucketName,
  normalizeS3FolderPath,
  normalizeS3MaxFilesInput,
  s3BucketFieldError,
} from './s3InputValidation'

describe('normalizeS3BucketName', () => {
  it('strips a leading s3:// prefix case-insensitively', () => {
    expect(normalizeS3BucketName('s3://my-bucket')).toBe('my-bucket')
    expect(normalizeS3BucketName('  S3://my-bucket  ')).toBe('my-bucket')
    expect(normalizeS3BucketName('my-bucket')).toBe('my-bucket')
  })
})

describe('s3 bucket validation', () => {
  it('requires a non-empty bucket name', () => {
    expect(s3BucketFieldError('')).toBe('Enter the S3 bucket name before continuing.')
    expect(s3BucketFieldError('   ')).toBe('Enter the S3 bucket name before continuing.')
    expect(isValidS3BucketName('')).toBe(false)
  })

  it('accepts bucket names with or without s3:// after normalization', () => {
    expect(s3BucketFieldError('s3://my-bucket')).toBeNull()
    expect(isValidS3BucketName('s3://my-bucket')).toBe(true)
    expect(s3BucketFieldError('my-bucket')).toBeNull()
    expect(isValidS3BucketName('my-bucket')).toBe(true)
  })
})

describe('normalizeS3FolderPath', () => {
  it('returns empty for blank or slash-only values', () => {
    expect(normalizeS3FolderPath('')).toBe('')
    expect(normalizeS3FolderPath('   ')).toBe('')
    expect(normalizeS3FolderPath('///')).toBe('')
  })

  it('adds a single trailing slash when missing', () => {
    expect(normalizeS3FolderPath('input/articles')).toBe('input/articles/')
    expect(normalizeS3FolderPath('input/')).toBe('input/')
  })

  it('collapses multiple trailing slashes to one', () => {
    expect(normalizeS3FolderPath('input/articles///')).toBe('input/articles/')
  })
})

describe('normalizeS3MaxFilesInput', () => {
  it('defaults empty or invalid input to 500', () => {
    expect(normalizeS3MaxFilesInput('')).toBe(500)
    expect(normalizeS3MaxFilesInput('abc')).toBe(500)
  })

  it('clamps parsed values between 1 and 10000', () => {
    expect(normalizeS3MaxFilesInput('250')).toBe(250)
    expect(normalizeS3MaxFilesInput('0')).toBe(1)
    expect(normalizeS3MaxFilesInput('999999')).toBe(10000)
  })
})
