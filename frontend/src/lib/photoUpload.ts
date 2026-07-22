import api from '@/lib/api'

export type PhotoUploadStatus = 'queued' | 'compressing' | 'uploading' | 'saving' | 'done' | 'error'

export interface PhotoUploadProgress {
  status: PhotoUploadStatus
  progress: number
  error?: string
}

interface DirectPhotoUploadSignature {
  cloud_name: string
  api_key: string
  timestamp: number
  signature: string
  folder: string
  upload_url: string
}

interface CloudinaryUploadResponse {
  secure_url: string
  public_id: string
}

export interface DirectPhotoUploadOptions {
  file: File
  signEndpoint: string
  recordEndpoint: string
  fallbackEndpoint?: string
  fallbackMode?: 'multipart' | 'base64-json'
  caption?: string
  onProgress?: (progress: PhotoUploadProgress) => void
}

const MAX_UPLOAD_DIMENSION = 1800
const JPEG_QUALITY = 0.82
const CLOUDINARY_UPLOAD_CONCURRENCY = 3

const imageMimeTypes = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'])

export function isSupportedPhotoFile(file: File) {
  return file.type.startsWith('image/') && (imageMimeTypes.has(file.type.toLowerCase()) || file.type === '')
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function loadImage(file: File): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(file)
  try {
    const image = new Image()
    image.decoding = 'async'
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('Could not read selected image'))
      image.src = url
    })
    return image
  } finally {
    URL.revokeObjectURL(url)
  }
}

async function compressPhoto(file: File): Promise<File> {
  if (!file.type.startsWith('image/') || file.type === 'image/heic' || file.type === 'image/heif') {
    return file
  }

  try {
    const image = await loadImage(file)
    const scale = Math.min(1, MAX_UPLOAD_DIMENSION / Math.max(image.naturalWidth, image.naturalHeight))
    if (scale >= 1 && file.type === 'image/jpeg' && file.size < 1.5 * 1024 * 1024) {
      return file
    }

    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
    const context = canvas.getContext('2d')
    if (!context) return file
    context.drawImage(image, 0, 0, canvas.width, canvas.height)

    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY))
    if (!blob || blob.size >= file.size) return file

    const baseName = file.name.replace(/\.[^.]+$/, '') || 'photo'
    return new File([blob], `${baseName}.jpg`, { type: 'image/jpeg', lastModified: Date.now() })
  } catch {
    return file
  }
}

function uploadToCloudinary(signature: DirectPhotoUploadSignature, file: File, onProgress?: (percent: number) => void) {
  return new Promise<CloudinaryUploadResponse>((resolve, reject) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('api_key', signature.api_key)
    formData.append('timestamp', String(signature.timestamp))
    formData.append('signature', signature.signature)
    formData.append('folder', signature.folder)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', signature.upload_url)
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onload = () => {
      let payload: any = null
      try {
        payload = JSON.parse(xhr.responseText)
      } catch {
        reject(new Error('Cloudinary returned an unreadable upload response'))
        return
      }
      if (xhr.status >= 200 && xhr.status < 300 && payload?.secure_url && payload?.public_id) {
        resolve({ secure_url: payload.secure_url, public_id: payload.public_id })
        return
      }
      reject(Object.assign(new Error(payload?.error?.message || 'Cloudinary upload failed'), { status: xhr.status }))
    }
    xhr.onerror = () => reject(Object.assign(new Error('Network error while uploading photo'), { status: xhr.status }))
    xhr.send(formData)
  })
}

function isMethodNotAllowed(error: unknown) {
  if ((error as any)?.response?.status === 405 || (error as any)?.status === 405) return true
  const message = error instanceof Error ? error.message : String(error || '')
  return message.toLowerCase().includes('method not allowed')
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
    reader.readAsDataURL(file)
  })
}

async function uploadViaAppEndpoint<TPhoto>(
  endpoint: string,
  file: File,
  caption: string | undefined,
  mode: 'multipart' | 'base64-json',
  onProgress?: (progress: PhotoUploadProgress) => void,
) {
  onProgress?.({ status: 'uploading', progress: 18 })
  if (mode === 'base64-json') {
    const image = await readFileAsDataUrl(file)
    const response = await api.post<TPhoto>(
      endpoint,
      { image, caption: caption?.trim() || undefined },
      {
        onUploadProgress: (event) => {
          if (!event.total) return
          onProgress?.({ status: 'uploading', progress: 18 + Math.round((event.loaded / event.total) * 72) })
        },
      },
    )
    onProgress?.({ status: 'done', progress: 100 })
    return response.data
  }

  const formData = new FormData()
  formData.append('image', file)
  if (caption?.trim()) formData.append('caption', caption.trim())
  const response = await api.post<TPhoto>(endpoint, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (!event.total) return
      onProgress?.({ status: 'uploading', progress: 18 + Math.round((event.loaded / event.total) * 72) })
    },
  })
  onProgress?.({ status: 'done', progress: 100 })
  return response.data
}

export async function uploadDirectPhoto<TPhoto>({
  file,
  signEndpoint,
  recordEndpoint,
  fallbackEndpoint,
  fallbackMode = 'multipart',
  caption,
  onProgress,
}: DirectPhotoUploadOptions) {
  onProgress?.({ status: 'compressing', progress: 5 })
  const compressedFile = await compressPhoto(file)
  onProgress?.({ status: 'uploading', progress: 15 })

  try {
    const signature = (await api.post<DirectPhotoUploadSignature>(signEndpoint)).data
    const uploaded = await uploadToCloudinary(signature, compressedFile, (percent) => {
      onProgress?.({ status: 'uploading', progress: 15 + Math.round(percent * 0.75) })
    })

    onProgress?.({ status: 'saving', progress: 92 })
    const response = await api.post<TPhoto>(recordEndpoint, {
      image_url: uploaded.secure_url,
      public_id: uploaded.public_id,
      caption: caption?.trim() || undefined,
    })
    onProgress?.({ status: 'done', progress: 100 })
    return response.data
  } catch (error) {
    if (fallbackEndpoint && isMethodNotAllowed(error)) {
      return uploadViaAppEndpoint<TPhoto>(fallbackEndpoint, compressedFile, caption, fallbackMode, onProgress)
    }
    throw error
  }
}

export async function runPhotoUploadQueue<TFile>(
  items: TFile[],
  worker: (item: TFile) => Promise<void>,
  concurrency = CLOUDINARY_UPLOAD_CONCURRENCY,
) {
  let cursor = 0
  const workers = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (cursor < items.length) {
      const index = cursor
      cursor += 1
      await worker(items[index])
    }
  })
  await Promise.all(workers)
}
