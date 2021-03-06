from PIL import Image
import numpy as np
import cv2
from functools import reduce
from os.path import basename, join
import os
import sys
from matplotlib.pyplot import plot, imshow, show, colorbar

def remove_background(im, threshold):
  mask = im < threshold
  imMasked = im.copy()
  imMasked[mask] = 0
  return imMasked

def merge_patch(imBase, imPatch, centroid, threshold=100):
  '''Takes imPatch and superimpose on imBase at centroid. Returns modified image'''

  imBase, imPatch = 255-imBase, 255-imPatch # invert images fro processing
  nrb, ncb = imBase.shape
  nrp, ncp = imPatch.shape

  # make white areas of imPatch transparent
  imPatchMasked = remove_background(imPatch, threshold)

  # get difference of centroids between base and patch
  centroidPatch = np.array([int(dim/2) for dim in imPatchMasked.shape])
  delta = np.array(centroid) - centroidPatch

  # add difference of centroids to the x,y position of patch
  cc, rr = np.meshgrid(np.arange(ncp), np.arange(nrp))
  rr = rr + int(delta[0])
  cc = cc + int(delta[1])

  # remove all parts of patch image that would expand base image
  keep = reduce(np.logical_and, [rr>=0, rr<nrb, cc>=0, cc<ncb])
  nrk, nck = np.max(rr[keep])-np.min(rr[keep])+1, np.max(cc[keep])-np.min(cc[keep])+1
  imPatchKeep = imPatchMasked[keep]


  # merge base and patch by taking maximum pixel at each position
  imMerge = imBase.copy()
  imBaseCrop = imBase.copy()
  imBaseCrop = imBaseCrop[rr[keep], cc[keep]]
  imMerge[rr[keep], cc[keep]] = np.maximum(imBaseCrop, imPatchKeep)

  return 255-imMerge # invert back

def clean_lines(img, threshold=.23):
  '''use hough transnform to remove lines from the ey dataset'''
  img_copy = img.copy()
  if len(img.shape)>2: gray = cv2.cvtColor(img_copy, cv2.COLOR_BGR2GRAY)
  else: gray = img_copy.copy()
  largerDim = np.max(gray.shape)
  origShape = gray.shape
  sqrShape = [largerDim, largerDim]

  # image preprocessing for the hough transform
  gray = cv2.resize(gray, (largerDim, largerDim)) # resize to be square so that votes for both horz and vert lines are equal
  gray = cv2.GaussianBlur(gray,(5,5),0)
  edges = cv2.Canny(gray, 50, 150, apertureSize=3) # edge detection
  # Image.fromarray(edges).show() # debug

  # apply hough transform
  width = edges.shape[0]
  thresholdPix = int( threshold * width ) # threshold is percentage of full image width expected to get votes
  lines = cv2.HoughLines(edges, 1, 1 * np.pi / 180, threshold=thresholdPix)

  # loop over detected lines in hough space and convert to euclidean
  for rho, theta in np.squeeze(lines):
    # leverage the fact that we know the lines occur at the borders of the image and are horz or vert
    conditionTheta = (abs(180/np.pi * theta - 0  ) < 3) | \
                     (abs(180/np.pi * theta - 90 ) < 3) | \
                     (abs(180/np.pi * theta - 180) < 3) | \
                     (abs(180/np.pi * theta - 270) < 3) | \
                     (abs(180/np.pi * theta - 360) < 3)
    conditionRho = (abs(180/np.pi * theta - 0  ) < 3) & (abs(rho - 0    ) < .07*width) | \
                   (abs(180/np.pi * theta - 0  ) < 3) & (abs(rho - width) < .07*width) | \
                   (abs(180/np.pi * theta - 0  ) < 3) & (abs(rho + width) < .07*width) | \
                   (abs(180/np.pi * theta - 180) < 3) & (abs(rho - 0    ) < .07*width) | \
                   (abs(180/np.pi * theta - 180) < 3) & (abs(rho - width) < .07*width) | \
                   (abs(180/np.pi * theta - 180) < 3) & (abs(rho + width) < .07*width) | \
                   (abs(180/np.pi * theta - 90) < 3) & (abs(rho - 0    ) < .2*width) | \
                   (abs(180/np.pi * theta - 90) < 3) & (abs(rho - width) < .2*width) | \
                   (abs(180/np.pi * theta - 90) < 3) & (abs(rho + width) < .2*width)
    # draw the lines
    if conditionTheta & conditionRho:
      # plot( rho, theta, 'or' , markersize=4) # debug
      a = np.cos(theta)
      b = np.sin(theta)
      x0 = a * rho
      y0 = b * rho
      x1 = int(x0 + 1000 * (-b))
      y1 = int(y0 + 1000 * (a))
      x2 = int(x0 - 1000 * (-b))
      y2 = int(y0 - 1000 * (a))
      # scale back to original image size
      x1 = int( x1 * origShape[1]/sqrShape[1] )
      x2 = int( x2 * origShape[1]/sqrShape[1] )
      y1 = int( y1 * origShape[0]/sqrShape[0] )
      y2 = int( y2 * origShape[0]/sqrShape[0] )
      cv2.line(img_copy, (x1, y1), (x2, y2), (255, 255, 255), thickness=14)
    else:
      # plot( rho, theta, '.b' , markersize=4) # debug
      pass
  return img_copy

def tight_crop(img, threshold=1-1.5e-2):
  '''tightly crop an image, removing whitespace'''
  img_copy = 255 - img
  if len(img_copy.shape)>2: img_copy = cv2.cvtColor(img_copy, cv2.COLOR_BGR2GRAY)
  img_copy[img_copy>20] = 255 # binarize
  img_copy[img_copy<=20] = 0
  # Image.fromarray(img_copy).show() # debug
  img_copy = cv2.erode(img_copy, np.ones((3,3)))

  # function: whiten the border given the crop coordinates
  def clean_border(img, r1, r2, c1, c2, debug=False):
    img_copy = img.copy()
    if debug:
      img_copy[:r1, :]  = 125
      img_copy[-r2:, :] = 125
      img_copy[:, :c1]  = 125
      img_copy[:, -c2:] = 125
    else:
      img_copy[:r1, :]  = 0
      img_copy[-r2:, :] = 0
      img_copy[:, :c1]  = 0
      img_copy[:, -c2:] = 0
    return img_copy

  # function: calculate ratio of preserved black pixels after the border cleaning
  ratio_preserved = lambda crop: np.sum(clean_border(img_copy, crop[0], crop[1], crop[2], crop[3])) / np.sum(img_copy)

  # iteratively crop more and more on each side alternatingly till preservedRatio hits threshold
  crop = [0,1,0,1]
  edgeId = -1
  subThreshold = 1
  increment = .5e-3
  while subThreshold >= threshold:
    edgeId += 1
    subThreshold -= increment
    nextCrop = crop.copy()
    while ratio_preserved(nextCrop) >= subThreshold:
      crop = nextCrop.copy()
      nextCrop[np.mod(edgeId,4)] += 1
    # Image.fromarray(clean_border(img_copy, crop[0], crop[1], crop[2], crop[3], debug=True)).show()
    # print(crop, np.mod(edgeId,4), ratio_preserved(crop), subThreshold)

  return img[crop[0]:-crop[1], crop[2]:-crop[3]] # crop the image and return

if __name__ == '__main__':
  file = '/Users/dl367ny/htrdata/crowdsource/extracted/111003/$9,900,000.jpg'
  patchFile = '/Users/dl367ny/htrdata/cropped_patches/nw_horizontal-2/Declined - Handwritten (1)_Redacted-2-aligned-Unnamed2.jpg'
  imBase = cv2.imread(file, cv2.IMREAD_GRAYSCALE)
  im = cv2.imread(patchFile, cv2.IMREAD_GRAYSCALE)
  im = cv2.resize(im, None, fx=3, fy=1)+50

  nrb, ncb = imBase.shape
  centroid = int(.4*nrb), int(ncb/2)
  imMerge = merge_patch(imBase, im, centroid, 100)
  Image.fromarray(imMerge).show()
