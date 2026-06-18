import { describe, expect, it } from 'vitest'

import { s3InputSourceFromGraphSpec } from './s3InputSource'

describe('s3InputSourceFromGraphSpec', () => {
  it('returns null when the flow has no S3 input node', () => {
    expect(
      s3InputSourceFromGraphSpec({
        nodes: [{ type: 'TextInput', params: { text: 'hello' } }],
      }),
    ).toBeNull()
  })

  it('returns null when the S3 bucket is missing', () => {
    expect(
      s3InputSourceFromGraphSpec({
        nodes: [{ type: 'S3Input', params: { folder_path: 'input/' } }],
      }),
    ).toBeNull()
  })

  it('builds an s3 uri from bucket and folder path', () => {
    expect(
      s3InputSourceFromGraphSpec({
        nodes: [
          {
            type: 'S3Input',
            params: { bucket: 's3://my-bucket', folder_path: 'input/articles/' },
          },
        ],
      }),
    ).toEqual({
      bucket: 'my-bucket',
      folderPath: 'input/articles/',
      uri: 's3://my-bucket/input/articles/',
    })
  })

  it('uses bucket root when folder path is empty', () => {
    expect(
      s3InputSourceFromGraphSpec({
        nodes: [{ type: 'S3Input', params: { bucket: 'my-bucket', folder_path: '' } }],
      }),
    ).toEqual({
      bucket: 'my-bucket',
      folderPath: '',
      uri: 's3://my-bucket/',
    })
  })
})
